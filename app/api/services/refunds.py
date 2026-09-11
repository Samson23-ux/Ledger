import sentry_sdk
from uuid import UUID, uuid7
import sentry_sdk.logger as sentry_logger


from app.api.models.user import User
from app.util import get_user_email
from app.api.schemas.outbox import OutBoxCreate
from app.api.repo.outbox import OutBoxRepository
from app.api.repo.uow import UnitOfWorkRepository
from app.api.services.outbox import OutBoxService
from app.api.repo.refunds import RefundRepository
from app.api.services.thread_pool import ThreadPool
from app.api.schemas.refund_state import RefundStateCreate
from app.api.repo.transactions import TransactionRepository
from app.api.repo.refund_state import RefundStateRepository
from app.api.services.transactions import TransactionService
from app.api.services.refund_state import RefundStateService
from app.api.schemas.refunds import RefundCreate, RefundResponse, RetryRefund
from app.core.exceptions import (
    ServerError,
    RefundNotFoundError,
    RefundsNotFoundError,
    RefundStateNotFoundError,
    TransactionNotFoundError,
)


class RefundService:
    def __init__(self, pool: ThreadPool, refund_repo: RefundRepository):
        self._pool = pool
        self._refund_repo = refund_repo

    async def _setup_uow(self, uow: UnitOfWorkRepository):
        self._uow = uow

    async def _uow_refund(self, uow: UnitOfWorkRepository):
        await self._setup_uow(uow)

        out_box_repo = self._uow.repo(OutBoxRepository)
        state_repo = self._uow.repo(RefundStateRepository)
        transaction_repo = self._uow.repo(TransactionRepository)

        self._out_box_service = OutBoxService(out_box_repo=out_box_repo)
        self._state_service = RefundStateService(state_repo=state_repo)
        self._transaction_service = TransactionService(
            pool=self._pool, transaction_repo=transaction_repo
        )

    def _get_refund_payload(
        self, transaction_id: UUID, amount: str, currency: str, customer_note: str
    ) -> tuple[RefundCreate, RefundStateCreate]:
        refund_create = RefundCreate(
            id=uuid7(),
            payment_transaction_id=transaction_id,
            amount=amount,
            currency=currency,
            customer_note=customer_note,
            merchant_note="",
        )

        refund_state = RefundStateCreate(
            refund_id=refund_create.id, to_status="pending", source="user_action"
        )

        return refund_create, refund_state

    async def _get_outbox_payload(
        self, transaction_id: UUID, wallet_id: UUID, email: str, amount: str
    ) -> OutBoxCreate:
        out_box_id = uuid7()
        return OutBoxCreate(
            id=out_box_id,
            event_type="refund",
            payload={
                "out_box_id": out_box_id,
                "email": email,
                "amount": amount,
                "currency": "NGN",
                "transaction_id": transaction_id,
                "wallet_id": wallet_id,
            },
        )

    async def request_for_refund(
        self, id: UUID, customer_note: str, curr_user: User, uow: UnitOfWorkRepository
    ):
        try:
            await self._setup_uow(uow)

            user_id = curr_user.id
            user_email = get_user_email(curr_user)

            transaction = await self._transaction_service._get_transaction(
                id=id, user_id=user_id, status="success"
            )

            if not transaction:
                sentry_logger.error(
                    "Transaction not found",
                    extra={"user_id": user_id, "transaction_id": id},
                )
                raise TransactionNotFoundError(id=id)

            refund_create, refund_state = self._get_refund_payload(
                transaction.id, transaction.amount, transaction.currency, customer_note
            )

            self._refund_repo.add(entity=refund_create)
            await self._state_service._create_refund_state(refund_state)

            outbox_create = self._get_outbox_payload(
                transaction.id, transaction.wallet_id, user_email, transaction.amount
            )
            await self._out_box_service._create_out_box(outbox_create)

            # request for refund in celery task

            sentry_logger.info(
                "Refund initiated successfully",
                extra={"user_id": user_id, "transaction_id": transaction.id},
            )
        except Exception as exc:
            if isinstance(exc, TransactionNotFoundError):
                raise TransactionNotFoundError(id=id)

            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while requesting for refund",
                extra={"user_id": user_id, "transaction_id": id},
            )
            raise ServerError() from exc

    async def get_refunds(
        self,
        curr_user: User,
        cursor: str | None,
        sort: str | None,
        order: str,
        limit: int,
    ) -> list[RefundResponse]:
        try:
            user_id = curr_user.id

            res = await self._refund_repo.get_records(
                sort, order, cursor, limit, user_id=user_id
            )

            if not res:
                sentry_logger.error("Refunds not found", extra={"user_id": user_id})
                raise RefundsNotFoundError()

            refunds_db = res.get("data")

            refunds = []
            for refund in refunds_db:
                refunds.append(RefundResponse.model_validate(refund))

            sentry_logger.info(
                "Refunds retrieved successfully", extra={"user_id": user_id}
            )
            return refunds, res.get("cursor")
        except Exception as exc:
            if isinstance(exc, RefundsNotFoundError):
                raise RefundsNotFoundError()

            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while retrieving refunds",
                extra={"user_id": user_id},
            )
            raise ServerError() from exc

    async def get_refund(self, id: UUID, curr_user: User) -> RefundResponse:
        try:
            user_id = curr_user.id
            refund = await self._refund_repo.get_record(id=id, user_id=user_id)

            if not refund:
                sentry_logger.error(
                    "Refund not found",
                    extra={"user_id": user_id, "refund_id": id},
                )
                raise RefundNotFoundError(id=id)

            sentry_logger.info(
                "Refund retrieved successfully",
                extra={"user_id": user_id, "refund_id": id},
            )
            return RefundResponse.model_validate(refund)
        except Exception as exc:
            if isinstance(exc, RefundNotFoundError):
                raise RefundNotFoundError(id=id)

            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while retrieving refund",
                extra={"user_id": user_id, "refund_id": id},
            )
            raise ServerError() from exc

    async def retry_refund(
        self,
        id: UUID,
        curr_user: User,
        retry_payload: RetryRefund,
        uow: UnitOfWorkRepository,
    ):
        try:
            await self._setup_uow(uow)

            user_id = curr_user.id
            user_email = get_user_email(curr_user)

            refund = await self._refund_repo.get_record(
                id=id, user_id=user_id, status="needs_attention"
            )

            if not refund:
                sentry_logger.error(
                    "Refund not found",
                    extra={"user_id": user_id, "refund_id": id},
                )
                raise RefundNotFoundError(id=id)

            refund_create, refund_state = self._get_refund_payload(
                refund.payment_transaction_id,
                refund.amount,
                refund.currency,
                refund.customer_note,
            )

            self._refund_repo.add(entity=refund_create)
            await self._state_service._create_refund_state(refund_state)

            outbox_create = self._get_outbox_payload(
                refund.payment_transaction_id,
                refund.transaction.wallet_id,
                user_email,
                refund.amount,
            )
            await self._out_box_service._create_out_box(outbox_create)

            # retry request for refund in celery task

            sentry_logger.info(
                "Retried refund successfully",
                extra={
                    "user_id": user_id,
                    "transaction_id": refund.payment_transaction_id,
                },
            )
        except Exception as exc:
            if isinstance(exc, RefundNotFoundError):
                raise RefundNotFoundError(id=id)

            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while retrying refund with account details",
                extra={"user_id": user_id, "refund_id": id},
            )
            raise ServerError() from exc
