import sentry_sdk
from uuid import UUID, uuid7
import sentry_sdk.logger as sentry_logger
from paystack import exceptions as PaystackException
from datetime import date, datetime, timezone, timedelta


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
from app.worker.tasks.charge_authorization import charge_authorization
from app.api.schemas.transactions import TransactionCreate, TransactionResponse
from app.core.exceptions import (
    ServerError,
    ServiceUnavailable,
    AuthenticationError,
    WalletCreditNotFoundError,
    WalletCreditsNotFoundError,
)

FUND_CALLBACK_TTL = 60 * 60 * 24  # 1 day


def _fund_callback_key(reference: str, user_id: UUID) -> str:
    return f"wallet_fund_callback:{reference}:{user_id}"


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
            pool=ThreadPool(),
            transaction_repo=transaction_repo
        )
        self._out_box_service = OutBoxService(out_box_repo=out_box_repo)
        self._auth_code_service = AuthCodeService(code_repo=auth_code_repo)
        self._state_service = TransactionStateService(state_repo=state_repo)

    async def _uow_wallet_callback(self, uow: UnitOfWorkRepository):
        await self._setup_uow(uow)

        state_repo = self._uow.repo(TransactionStateRepository)
        transaction_repo = self._uow.repo(TransactionRepository)

        self._transaction_service = TransactionService(
            pool=ThreadPool(),
            transaction_repo=transaction_repo
        )
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
            created_at=datetime.now(timezone.utc)
        )

        state_create: TransactionStateCreate = TransactionStateCreate(
            transaction_id=transaction_create.id,
            status="pending",
            source="user_action",
        )

        return transaction_create, state_create

    async def _get_outbox_payload(
        self,
        out_box_id: UUID,
        email: str,
        amount: str,
        code: str,
        transaction_id: UUID,
    ) -> OutBoxCreate:
        return OutBoxCreate(
            id=out_box_id,
            event_type="charge_authorization",
            payload={
                "email": email,
                "amount": str(amount),
                "currency": "NGN",
                "authorization_code": code,
                "transaction_id": str(transaction_id),
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
            wallet: Wallet = await self._get_wallet(user_id)

            transaction_create, state_create = await self._get_transaction_payloads(
                idempotency_key,
                user_id,
                wallet.id,
                fund_wallet.amount,
                fund_wallet.channel,
            )

            # Insert a bare "pending" row first, before doing any Paystack
            # work. Postgres blocks a concurrent INSERT...ON CONFLICT on the
            # same idempotency_key until this transaction resolves, so this
            # single statement is what arbitrates concurrent duplicate
            # requests - only the request whose row this is proceeds to
            # actually call Paystack; everyone else waits here and then just
            # reads back the finished result. If we end up rolling back
            # (Paystack call fails, process crashes, ...) the insert unwinds
            # with it, so a waiting duplicate falls through to a fresh
            # insert of its own instead of being stuck behind a dead row.
            transaction = await self._transaction_service._create_transaction(
                transaction_create
            )
            is_owner = transaction.id == transaction_create.id

            if not is_owner:
                await self._uow.commit()
                sentry_logger.info(
                    "Duplicate wallet fund request resolved to existing "
                    "transaction",
                    extra={"user_id": user_id},
                )
                # the checkout url is only still usable while the owner's
                # attempt is sitting at "pending" - once it moves past that
                # (the callback route or a webhook already reached it), the
                # url has been consumed and Paystack will show a "We could
                # not start this transaction" page instead of the real result.
                if transaction.status == "pending" and transaction.authorization_url:
                    return transaction.authorization_url
                return TransactionResponse.model_validate(transaction)

            await self._state_service._create_transaction_state(state_create)

            initialize = True

            if fund_wallet.channel == "card":
                # check if the wallet has an authorization_code to prevent collection of card details
                auth_code: AuthorizationCode | None = (
                    await self._auth_code_service._get_auth_code(wallet_id=wallet.id)
                )

                if auth_code:
                    exp_year, exp_month = int(auth_code.exp_year), int(
                        auth_code.exp_month
                    )

                    # a card is valid through the end of its expiry month
                    if exp_month == 12:
                        expires_at = date(exp_year + 1, 1, 1)
                    else:
                        expires_at = date(exp_year, exp_month + 1, 1)

                    today = datetime.now(timezone.utc).date()

                    # check usability and validity
                    if auth_code.reusable and today < expires_at:
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
                    amount=str(fund_wallet.amount),
                    currency="NGN",
                    channel=fund_wallet.channel,
                )

                transaction.paystack_reference = initialization["data"]["reference"]
                transaction.authorization_url = initialization["data"][
                    "authorization_url"
                ]

                await self._redis_repo.set_key(
                    _fund_callback_key(transaction.paystack_reference, user_id),
                    str(user_id),
                    FUND_CALLBACK_TTL,
                )

                await self._transaction_service._update_transaction(transaction)
            else:
                transaction.authorization_code = auth_code.code
                await self._transaction_service._update_transaction(transaction)

                out_box_id: UUID = uuid7()
                out_box_create = await self._get_outbox_payload(
                    out_box_id,
                    user_email,
                    fund_wallet.amount,
                    auth_code.code,
                    transaction.id,
                )

                await self._out_box_service._create_out_box(out_box_create)

                transaction_response = TransactionResponse.model_validate(transaction)

            await self._uow.commit()

            if not initialize:
                # only dispatch once the transaction and outbox rows are
                # actually committed - the worker reads them on its own DB
                # connection and won't see them otherwise, silently no-oping
                # and leaving the outbox row stuck "pending"
                charge_authorization.apply_async(
                    priority=5,
                    kwargs={
                        "out_box_id": str(out_box_id),
                        "email": user_email,
                        "amount": str(fund_wallet.amount),
                        "currency": "NGN",
                        "message_id": str(uuid7()),
                        "transaction_id": str(transaction.id),
                        "authorization_code": auth_code.code,
                    },
                )

            sentry_logger.info("Wallet fund initiated", extra={"user_id": user_id})

            await circuit.record_success()
            return transaction.authorization_url if initialize else transaction_response
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
        self, reference: str, uow: UnitOfWorkRepository
    ) -> TransactionResponse:
        try:
            await self._uow_wallet_callback(uow)

            transaction = await self._transaction_service._get_transaction(
                paystack_reference=reference
            )

            if not transaction:
                sentry_logger.error(
                    "Transaction not found for callback",
                    extra={"reference": reference},
                )
                raise AuthenticationError()

            callback_key = _fund_callback_key(reference, transaction.user_id)
            stored = await self._redis_repo.get_key(callback_key)

            if not stored:
                sentry_logger.error(
                    "Missing or expired fund callback record",
                    extra={"reference": reference, "user_id": transaction.user_id},
                )
                raise AuthenticationError()

            await self._redis_repo.delete_key(callback_key)

            if transaction.status == "pending":
                # Only move pending -> initiated here. The webhook is the
                # authoritative source for anything past that (success,
                # failed, ...) and may well have already landed by the time
                # the browser redirect gets back to us - never downgrade a
                # status it already advanced.
                transaction.status = "initiated"
                state_create: TransactionStateCreate = TransactionStateCreate(
                    transaction_id=transaction.id,
                    status="initiated",
                    source="user_action",
                )

                await self._transaction_service._update_transaction(transaction)
                await self._state_service._create_transaction_state(state_create)

            await self._uow.commit()

            sentry_logger.info(
                "Transaction retrieved successfully for callback",
                extra={"user_id": transaction.user_id},
            )
            return TransactionResponse.model_validate(transaction)
        except Exception as exc:
            await self._uow.rollback()

            if isinstance(exc, AuthenticationError):
                raise

            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while retrieving transaction record for callback",
                extra={"reference": reference},
            )
            raise ServerError() from exc
