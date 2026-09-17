from uuid import UUID
from typing import Annotated
from fastapi import APIRouter, Query, Form


from app.api.schemas.refund_state import RefundStateResponse
from app.api.schemas.transactions import TransactionResponse
from app.api.schemas.refunds import RefundResponse, RetryRefund
from app.api.schemas.transaction_state import TransactionStateResponse
from app.api.schemas.response import AllSuccessResponse, SuccessResponse
from app.deps import (
    CurrentActiveCachedUser,
    TransactionServiceDep,
    TransactionStateServiceDep,
    UnitOfWorkRepo,
    RefundServiceDep,
    RefundStateServiceDep,
)

router = APIRouter()


@router.get(
    "/transactions",
    status_code=200,
    description="Get all transactions",
    response_model=AllSuccessResponse[list[TransactionResponse]],
)
async def get_all_transactions(
    curr_user: CurrentActiveCachedUser,
    transaction_service: TransactionServiceDep,
    cursor: Annotated[
        str,
        Query(description="Cursor from the last received transactions"),
    ] = None,
    sort: Annotated[
        str, Query(description="Sort transactions by created_at or updated_at")
    ] = None,
    limit: Annotated[
        int, Query(description="Limit the number of transactions returned")
    ] = 10,
    order: Annotated[
        str,
        Query(description="Order transactions in ascending(asc) or descending(desc)"),
    ] = "asc",
):
    transactions, next_cursor = await transaction_service.get_transactions(
        curr_user, cursor, sort, order, limit
    )
    return AllSuccessResponse(
        message="Transactions retrieved sucessfully",
        data=transactions,
        cursor=next_cursor,
    )


@router.get(
    "/transactions/refunds",
    status_code=200,
    description="Get all refunds",
    response_model=AllSuccessResponse[list[RefundResponse]],
)
async def get_all_refunds(
    refund_service: RefundServiceDep,
    curr_user: CurrentActiveCachedUser,
    transaction_id: Annotated[
        UUID, Query(description="Optionally filter by transaction id")
    ] = None,
    cursor: Annotated[
        str,
        Query(description="Cursor from the last received refunds"),
    ] = None,
    sort: Annotated[
        str, Query(description="Sort refunds by created_at or updated_at")
    ] = None,
    limit: Annotated[
        int, Query(description="Limit the number of refunds returned")
    ] = 10,
    order: Annotated[
        str,
        Query(description="Order refunds in ascending(asc) or descending(desc)"),
    ] = "asc",
):
    refunds, next_cursor = await refund_service.get_refunds(
        curr_user, transaction_id, cursor, sort, order, limit
    )
    return AllSuccessResponse(
        message="Refunds retrieved sucessfully",
        data=refunds,
        cursor=next_cursor,
    )


@router.get(
    "/transactions/{id}",
    status_code=200,
    description="Get transaction by id",
    response_model=SuccessResponse[TransactionResponse],
)
async def get_transaction(
    id: UUID,
    curr_user: CurrentActiveCachedUser,
    transaction_service: TransactionServiceDep,
):
    transaction = await transaction_service.get_transaction(id, curr_user)
    return SuccessResponse(
        message="Transaction retrieved sucessfully", data=transaction
    )


@router.get(
    "/transactions/{id}/events",
    status_code=200,
    description="Get transaction state by id",
    response_model=SuccessResponse[list[TransactionStateResponse]],
)
async def get_transaction_state(
    id: UUID,
    curr_user: CurrentActiveCachedUser,
    state_service: TransactionStateServiceDep,
):
    state = await state_service.get_transaction_state(id, curr_user)
    return SuccessResponse(
        message="Transaction state retrieved sucessfully", data=state
    )


@router.post(
    "/transactions/{id}/refunds",
    status_code=201,
    description="Refund request for successful transaction",
    response_model=SuccessResponse,
)
async def request_for_refund(
    id: UUID,
    uow: UnitOfWorkRepo,
    refund_service: RefundServiceDep,
    curr_user: CurrentActiveCachedUser,
    customer_note: Annotated[str, Form(...)],
):
    await refund_service.request_for_refund(id, customer_note, curr_user, uow)
    return SuccessResponse(message="Refund initiated successfully")


@router.get(
    "/transactions/refunds/{id}",
    status_code=200,
    description="Get refund by id",
    response_model=SuccessResponse[RefundResponse],
)
async def get_refund(
    id: UUID,
    refund_service: RefundServiceDep,
    curr_user: CurrentActiveCachedUser,
):
    refund = await refund_service.get_refund(id, curr_user)
    return SuccessResponse(message="Refund retrieved sucessfully", data=refund)


@router.get(
    "/transactions/refunds/{id}/events",
    status_code=200,
    description="Get refund state by id",
    response_model=SuccessResponse[list[RefundStateResponse]],
)
async def get_refund_state(
    id: UUID,
    state_service: RefundStateServiceDep,
    curr_user: CurrentActiveCachedUser,
):
    state = await state_service.get_refund_state(id, curr_user)
    return SuccessResponse(message="Refund state retrieved sucessfully", data=state)


@router.post(
    "/transactions/refunds/{id}/details",
    status_code=201,
    description="Provide bank account details to retry refund",
    response_model=SuccessResponse,
)
async def retry_refund(
    id: UUID,
    uow: UnitOfWorkRepo,
    retry_payload: RetryRefund,
    refund_service: RefundServiceDep,
    curr_user: CurrentActiveCachedUser,
):
    await refund_service.retry_refund_request(id, curr_user, retry_payload, uow)
    return SuccessResponse(message="Refund retried successfully")
