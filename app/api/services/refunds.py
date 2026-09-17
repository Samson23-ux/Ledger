import sentry_sdk
from uuid import UUID, uuid7
import sentry_sdk.logger as sentry_logger


from app.api.models.user import User
from app.api.models.refunds import Refund
from app.api.repo.redis import RedisRepository
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
from app.worker.tasks.refunds import request_refund, retry_refund as retry_refund_task
from app.core.exceptions import (
    ServerError,
    RefundNotFoundError,
    RefundsNotFoundError,
    TransactionNotFoundError,
)


class RefundService:
    def __init__(
        self,
        pool: ThreadPool,
        redis_repo: RedisRepository,
        refund_repo: RefundRepository,
    ):
        self._pool = pool
        self._redis_repo = redis_repo
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

    def _get_pending_refunds(self, **filters):
        return self._refund_repo.get_pending_refunds(**filters)

    def _get_refund_sync(self, **filters) -> Refund:
        return self._refund_repo.get_sync_record(**filters)

    def _update_refund_sync(self, refund: Refund):
        self._refund_repo.sync_add(model=refund)

    def _get_refund_payload(
        self,
        user_id: UUID,
        transaction_id: UUID,
        amount: str,
        currency: str,
        customer_note: str,
    ) -> tuple[RefundCreate, RefundStateCreate]:
        refund_create = RefundCreate(
            id=uuid7(),
            user_id=user_id,
            payment_transaction_id=transaction_id,
            amount=amount,
            currency=currency,
            customer_note=customer_note,
            merchant_note="Refund requested by customer",
        )

        refund_state = RefundStateCreate(
            refund_id=refund_create.id, status="pending", source="user_action"
        )

        return refund_create, refund_state

    def _update_refund_records(self, records: list[dict]):
        self._refund_repo._update_refund_records(records)

    async def _get_outbox_payload(
        self,
        reference: str,
        refund_id: UUID,
        customer_note: str,
        merchant_note: str,
        amount: str,
    ) -> OutBoxCreate:
        out_box_id = uuid7()
        return OutBoxCreate(
            id=out_box_id,
            event_type="request_refund",
            payload={
                "amount": str(amount),
                "currency": "NGN",
                "reference": reference,
                "refund_id": str(refund_id),
                "customer_note": customer_note,
                "merchant_note": merchant_note,
            },
        )

    async def _get_outbox_payload_retry(
        self,
        refund_id: UUID,
        existing_refund_id: int | None,
        account_number: str,
        bank_id: str,
    ) -> OutBoxCreate:
        out_box_id = uuid7()
        return OutBoxCreate(
            id=out_box_id,
            event_type="retry_refund",
            payload={
                "currency": "NGN",
                "bank_id": bank_id,
                "refund_id": str(refund_id),
                "existing_refund_id": existing_refund_id,
                "account_number": account_number,
            },
        )

    async def request_for_refund(
        self, id: UUID, customer_note: str, curr_user: User, uow: UnitOfWorkRepository
    ):
        try:
            await self._uow_refund(uow)

            resource_token = str(uuid7())
            user_id = curr_user.id

            create_refund = False
            token = await self._redis_repo.access_resource(
                f"refund:{id}", resource_token
            )

            if not token:
                return

            transaction = await self._transaction_service._get_transaction(
                id=id, user_id=user_id, status="success"
            )

            if not transaction:
                sentry_logger.error(
                    "Transaction not found",
                    extra={"user_id": user_id, "transaction_id": id},
                )
                raise TransactionNotFoundError(id=id)

            existing_refund = await self._refund_repo.get_refund(transaction.id)

            if not existing_refund:
                create_refund = True
            elif existing_refund and existing_refund.status == "failed":
                create_refund = True

            if create_refund:
                refund_create, refund_state = self._get_refund_payload(
                    user_id,
                    transaction.id,
                    transaction.amount,
                    transaction.currency,
                    customer_note,
                )

                self._refund_repo.add(entity=refund_create)
                await self._state_service._create_refund_state(refund_state)

                outbox_create = await self._get_outbox_payload(
                    transaction.paystack_reference,
                    refund_create.id,
                    customer_note,
                    refund_create.merchant_note,
                    transaction.amount,
                )
                await self._out_box_service._create_out_box(outbox_create)

                request_refund.apply_async(
                    priority=5,
                    kwargs={
                        "amount": str(transaction.amount),
                        "currency": transaction.currency,
                        "refund_id": str(refund_create.id),
                        "reference": transaction.paystack_reference,
                        "message_id": str(uuid7()),
                        "customer_note": customer_note,
                        "merchant_note": refund_create.merchant_note,
                    },
                )

            await self._redis_repo.release_lock(f"refund:{id}", resource_token)
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
        transaction_id: UUID,
        cursor: str | None,
        sort: str | None,
        order: str,
        limit: int,
    ) -> list[RefundResponse]:
        try:
            user_id = curr_user.id
            filters = {"user_id": user_id}

            if transaction_id:
                filters["transaction_id"] = transaction_id

            res = await self._refund_repo.get_records(
                sort, order, cursor, limit, **filters
            )

            refunds_db = res.get("data")
            if not refunds_db:
                sentry_logger.error("Refunds not found", extra={"user_id": user_id})
                raise RefundsNotFoundError()

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

    async def retry_refund_request(
        self,
        id: UUID,
        curr_user: User,
        retry_payload: RetryRefund,
        uow: UnitOfWorkRepository,
    ):
        try:
            await self._uow_refund(uow)

            user_id = curr_user.id
            resource_token = str(uuid7())

            token = await self._redis_repo.access_resource(
                f"retry_refund:{id}", resource_token
            )

            if not token:
                return

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
                user_id,
                refund.payment_transaction_id,
                refund.amount,
                refund.currency,
                refund.customer_note,
            )

            self._refund_repo.add(entity=refund_create)
            await self._state_service._create_refund_state(refund_state)

            outbox_create = await self._get_outbox_payload_retry(
                refund_create.id,
                refund.paystack_refund_id,
                retry_payload.account_number,
                retry_payload.bank_id,
            )
            await self._out_box_service._create_out_box(outbox_create)

            retry_refund_task.apply_async(
                priority=5,
                kwargs={
                    "currency": refund.currency,
                    "refund_id": str(refund_create.id),
                    "existing_refund_id": refund.paystack_refund_id,
                    "reference": refund.transaction.paystack_reference,
                    "message_id": str(uuid7()),
                    "account_number": retry_payload.account_number,
                    "bank_id": retry_payload.bank_id,
                },
            )

            await self._redis_repo.release_lock(f"retry_refund:{id}", resource_token)
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
