import sentry_sdk
from uuid import UUID, uuid7
import sentry_sdk.logger as sentry_logger
from datetime import datetime, timezone, timedelta
from paystack import exceptions as PaystackException


from app.util import get_user_email
from app.api.models.user import User
from app.api.models.wallets import Wallet
from app.api.schemas.wallets import WalletFund
from app.api.repo.redis import RedisRepository
from app.api.schemas.outbox import OutBoxCreate
from app.api.repo.outbox import OutBoxRepository
from app.api.repo.wallets import WalletRepository
from app.api.repo.uow import UnitOfWorkRepository
from app.api.services.outbox import OutBoxService
from app.api.services.thread_pool import ThreadPool
from app.api.services.payment_gateway import Transaction
from app.api.services.circuit_breaker import CircuitBreaker
from app.api.repo.transactions import TransactionRepository
from app.api.services.transactions import TransactionService
from app.api.services.wallet_credits import WalletCreditService
from app.api.repo.authorization_codes import AuthCodeRepository
from app.api.schemas.wallet_credits import WalletCreditResponse
from app.api.schemas.wallets import WalletCreate, WalletResponse
from app.api.models.authorization_codes import AuthorizationCode
from app.api.services.authorization_codes import AuthCodeService
from app.api.schemas.transaction_state import TransactionStateCreate
from app.api.repo.transaction_state import TransactionStateRepository
from app.api.services.transaction_state import TransactionStateService
from app.api.schemas.transactions import TransactionCreate, TransactionResponse
from app.core.exceptions import (
    ServerError,
    ServiceUnavailable,
    WalletCreditNotFoundError,
    WalletCreditsNotFoundError,
)


class WalletService:
    def __init__(
        self,
        pool: ThreadPool,
        wallet_repo: WalletRepository,
        redis_repo: RedisRepository,
    ):
        self._uow = None
        self._pool = pool
        self._redis_repo = redis_repo
        self._wallet_repo = wallet_repo

    async def _setup_uow(self, uow: UnitOfWorkRepository):
        self._uow = uow

    async def _uow_fund_wallet(self, uow: UnitOfWorkRepository):
        await self._setup_uow(uow)

        out_box_repo = self._uow.repo(OutBoxRepository)
        auth_code_repo = self._uow.repo(AuthCodeRepository)
        state_repo = self._uow.repo(TransactionStateRepository)
        transaction_repo = self._uow.repo(TransactionRepository)

        self._transaction_service = TransactionService(
            transaction_repo=transaction_repo
        )
        self._out_box_service = OutBoxService(out_box_repo=out_box_repo)
        self._auth_code_service = AuthCodeService(code_repo=auth_code_repo)
        self._state_service = TransactionStateService(state_repo=state_repo)

    async def _get_transaction_payloads(
        self,
        idempotency_key: str,
        user_id: UUID,
        wallet_id: UUID,
        amount: str,
        channel: str,
    ) -> tuple[TransactionCreate, TransactionStateCreate]:
        transaction_create: TransactionCreate = TransactionCreate(
            id=uuid7(),
            idempotency_key=idempotency_key,
            user_id=user_id,
            wallet_id=wallet_id,
            amount=amount,
            channel=channel,
        )

        state_create: TransactionStateCreate = TransactionStateCreate(
            transaction_id=transaction_create.id,
            to_status="pending",
            source="user_action",
        )

        return transaction_create, state_create

    async def _get_outbox_payload(
        self, email: str, amount: str, code: str
    ) -> OutBoxCreate:
        out_box_id = uuid7()
        return OutBoxCreate(
            id=out_box_id,
            event_type="charge_authorization",
            payload={
                "out_box_id": out_box_id,
                "email": email,
                "amount": amount,
                "currency": "NGN",
                "authorization_code": code,
            },
        )

    async def _get_wallet(self, user_id: UUID) -> Wallet:
        return await self._wallet_repo.get_record(user_id=user_id)

    async def _create_wallet(self, user_id: UUID):
        try:
            wallet_create = WalletCreate(user_id=user_id, balance="0")
            self._wallet_repo.add(entity=wallet_create)
        except Exception as exc:
            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while creating wallet", extra={"user_id": user_id}
            )
            raise ServerError() from exc

    async def fund_wallet(
        self,
        curr_user: User,
        gateway: Transaction,
        idempotency_key: str,
        circuit: CircuitBreaker,
        fund_wallet: WalletFund,
        uow: UnitOfWorkRepository,
    ) -> str | TransactionResponse:
        await self._uow_fund_wallet(uow)

        user_id: UUID = curr_user.id
        user_email: str = get_user_email(curr_user)

        try:
            transaction = await self._transaction_service._get_transaction(
                idempotency_key=idempotency_key
            )

            if transaction:
                sentry_logger.info(
                    "Existing payment transaction returned", extra={"user_id": user_id}
                )
                return TransactionResponse.model_validate(transaction)

            initialize = True
            wallet: Wallet = await self._get_wallet(user_id)

            transaction_create, state_create = await self._get_transaction_payloads(
                idempotency_key,
                user_id,
                wallet.id,
                fund_wallet.amount,
                fund_wallet.channel,
            )

            if fund_wallet.channel == "card":
                # check if the wallet has an authorization_code to prevent collection of card details
                auth_code: AuthorizationCode | None = (
                    await self._auth_code_service._get_auth_code(wallet_id=wallet.id)
                )

                if auth_code:
                    now = datetime.now(timezone.utc)
                    exp_year, exp_month = int(auth_code.exp_year), int(
                        auth_code.exp_month
                    )

                    # check usability and validity
                    if (
                        auth_code.reusable
                        and exp_year <= now.year
                        and exp_month < now.month
                    ):
                        initialize = False

            if initialize:
                # initialize transaction and collect card details

                state = await circuit.check()
                if not state["is_healthy"]:
                    sentry_logger.error("Paystack service unavailable")
                    raise ServiceUnavailable(retry_after=state["retry_after"])

                initialization = await self._pool.run_in_pool(
                    gateway.initialize_transaction,
                    email=user_email,
                    amount=fund_wallet.amount,
                    currency="NGN",
                    channel=fund_wallet.channel,
                )

                transaction_create.paystack_reference = initialization["data"][
                    "reference"
                ]
            else:
                transaction_create.authorization_code = auth_code.code

            await self._transaction_service._create_transaction(transaction_create)
            await self._state_service._create_transaction_state(state_create)

            if not initialize:
                out_box_create = self._get_outbox_payload(
                    user_email, fund_wallet.amount, auth_code.code
                )

                await self._out_box_service._create_out_box(out_box_create)

                ###### charge in celery worker

                transaction_response = TransactionResponse(
                    **transaction_create.model_dump()
                )

            await self._uow.commit()
            sentry_logger.info("Wallet fund initiated", extra={"user_id": user_id})

            await circuit.record_success()
            return (
                initialization["data"]["authorization_url"]
                if initialize
                else transaction_response
            )
        except PaystackException.ApiKeyError as exc:
            await self._uow.rollback()

            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while funding wallet.",
                extra={"details": "Invalid secret key", "user_id": user_id},
            )

            raise ServerError() from exc
        except PaystackException.UnauthorizedException as exc:
            await self._uow.rollback()

            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while funding wallet.",
                extra={
                    "details": "Unauthorized initialization request",
                    "user_id": user_id,
                },
            )

            raise ServerError() from exc
        except PaystackException.ServiceException as exc:
            await self._uow.rollback()

            state = await circuit.record_failure()
            if not state["is_healthy"]:
                raise ServiceUnavailable(retry_after=state["retry_after"])

            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while funding wallet.",
                extra={"details": "Service error", "user_id": user_id},
            )

            retry_after = (
                datetime.now(timezone.utc) + timedelta(seconds=30)
            ).isoformat()
            raise ServiceUnavailable(retry_after=retry_after) from exc
        except ServiceUnavailable as exc:
            raise exc
        except Exception as exc:
            await self._uow.rollback()

            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while funding wallet", extra={"user_id": user_id}
            )
            raise ServerError() from exc

    async def get_user_wallet(self, curr_user: User) -> WalletResponse:
        try:
            user_id = curr_user.id
            wallet: Wallet = await self._get_wallet(user_id)

            sentry_logger.info(
                "Wallet retrieved successfully", extra={"user_id": user_id}
            )
            return WalletResponse.model_validate(wallet)
        except Exception as exc:
            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while retrieving user wallet", extra={"user_id": user_id}
            )
            raise ServerError() from exc

    async def get_wallet_credit(
        self, id: UUID, curr_user: User, credit_service: WalletCreditService
    ) -> WalletCreditResponse:
        try:
            user_id = curr_user.id
            wallet: Wallet = await self._get_wallet(user_id)
            wallet_credit = await credit_service._get_wallet_credit(wallet.id, id)

            if not wallet_credit:
                sentry_logger.error(
                    "Wallet credit not found",
                    extra={"user_id": user_id, "credit_id": id},
                )
                raise WalletCreditNotFoundError(id=id)

            sentry_logger.info(
                "Wallet credit retrieved successfully",
                extra={"user_id": user_id, "credit_id": id},
            )
            return WalletCreditResponse.model_validate(wallet_credit)
        except Exception as exc:
            if isinstance(exc, WalletCreditNotFoundError):
                raise WalletCreditNotFoundError(id=id)

            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while retrieving user wallet credit",
                extra={"user_id": user_id},
            )
            raise ServerError() from exc

    async def get_wallet_credits(
        self,
        curr_user: User,
        credit_service: WalletCreditService,
        cursor: str | None,
        sort: str | None,
        order: str,
        limit: int,
    ) -> tuple:
        try:
            user_id = curr_user.id
            wallet: Wallet = await self._get_wallet(user_id)

            res = await credit_service._get_wallet_credits(
                cursor, sort, order, limit, wallet_id=wallet.id
            )
            credits = res.get("data")

            if not credits:
                sentry_logger.error(
                    "Wallet credits not found",
                    extra={"user_id": user_id},
                )
                raise WalletCreditsNotFoundError()

            credits_response = []
            for credit in credits:
                credits_response.append(WalletCreditResponse.model_validate(credit))

            sentry_logger.info("Wallet credits retrieved", extra={"user_id": user_id})
            return credits_response, res.get("cursor")
        except Exception as exc:
            if isinstance(exc, WalletCreditsNotFoundError):
                raise WalletCreditsNotFoundError()

            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while retrieving user wallet credits",
                extra={"user_id": user_id},
            )
            raise ServerError() from exc

    async def wallet_callback(
        self, curr_user: User, reference: str, transaction_service: TransactionService
    ) -> TransactionResponse:
        try:
            user_id = curr_user.id
            transaction = await transaction_service._get_transaction(
                paystack_reference=reference
            )

            sentry_logger.info(
                "Transaction retrieved successfully for callback",
                extra={"user_id": user_id},
            )
            return TransactionResponse.model_validate(transaction)
        except Exception as exc:
            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while retrieving transaction record for callback",
                extra={"user_id": user_id},
            )
            raise ServerError() from exc
