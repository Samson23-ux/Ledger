from uuid import UUID
from typing import Annotated
from fastapi import APIRouter, Request, Query
from fastapi.responses import RedirectResponse


from app.api.schemas.wallets import WalletFund
from app.api.schemas.wallets import WalletResponse
from app.api.schemas.transactions import TransactionResponse
from app.api.schemas.wallet_credits import WalletCreditResponse
from app.api.schemas.response import SuccessResponse, AllSuccessResponse
from app.deps import (
    get_default,
    TransactionDep,
    UnitOfWorkRepo,
    WalletServiceDep,
    CircuitBreakerDep,
    fund_wallet_limiter,
    TransactionServiceDep,
    WalletCreditServiceDep,
    CurrentActiveCachedUser,
)

router = APIRouter()


@router.get(
    "/wallets/me",
    status_code=200,
    dependencies=[get_default],
    description="Get current user wallet",
    response_model=SuccessResponse[WalletResponse],
)
async def get_wallet(
    wallet_service: WalletServiceDep,
    curr_user: CurrentActiveCachedUser,
):
    wallet = await wallet_service.get_user_wallet(curr_user)
    return SuccessResponse(message="Wallet retrieved successfully", data=wallet)


@router.get(
    "/wallets/me/credits",
    status_code=200,
    dependencies=[get_default],
    description="Get all wallet credit records",
    response_model=AllSuccessResponse[list[WalletCreditResponse]],
)
async def get_wallet_credits(
    wallet_service: WalletServiceDep,
    curr_user: CurrentActiveCachedUser,
    credit_service: WalletCreditServiceDep,
    cursor: Annotated[
        str,
        Query(description="Cursor from the last received credits"),
    ] = None,
    sort: Annotated[str, Query(description="Sort products by created_at")] = None,
    limit: Annotated[
        int, Query(description="Limit the number of credits returned")
    ] = 10,
    order: Annotated[
        str, Query(description="Order credits in ascending(asc) or descending(desc)")
    ] = "asc",
):
    credits, next_cursor = await wallet_service.get_wallet_credits(
        curr_user, credit_service, cursor, sort, order, limit
    )
    return AllSuccessResponse(
        message="Wallet credits retrieved successfully",
        data=credits,
        cursor=next_cursor,
    )


@router.get(
    "/wallets/me/credits/{id}",
    status_code=200,
    dependencies=[get_default],
    description="Get a wallet credit record",
    response_model=SuccessResponse[WalletCreditResponse],
)
async def get_wallet_credit(
    id: UUID,
    wallet_service: WalletServiceDep,
    curr_user: CurrentActiveCachedUser,
    credit_service: WalletCreditServiceDep,
):
    credit = await wallet_service.get_wallet_credit(id, curr_user, credit_service)
    return SuccessResponse(message="Wallet credit retrieved successfully", data=credit)


@router.get(
    "/wallets/fund/callback",
    status_code=200,
    dependencies=[get_default],
    description="Callback endpoint after initiating transaction",
    response_model=SuccessResponse[TransactionResponse],
)
async def wallet_fund_callback(
    request: Request,
    uow: UnitOfWorkRepo,
    wallet_service: WalletServiceDep,
    curr_user: CurrentActiveCachedUser,
    reference: Annotated[str, Query(...)],
):
    transaction = await wallet_service.wallet_callback(
        curr_user, reference, uow
    )
    return SuccessResponse(message="Transaction initiated", data=transaction)


@router.post(
    "/wallets/me/fund",
    status_code=201,
    dependencies=[fund_wallet_limiter],
    description="Fund existing wallet",
)
async def fund_wallet(
    request: Request,
    uow: UnitOfWorkRepo,
    fund_wallet: WalletFund,
    gateway: TransactionDep,
    circuit: CircuitBreakerDep,
    wallet_service: WalletServiceDep,
    curr_user: CurrentActiveCachedUser,
):
    idempotency_key: str = request.headers.get("x-idempotency-key")
    response = await wallet_service.fund_wallet(
        curr_user, gateway, idempotency_key, circuit, fund_wallet, uow
    )

    if isinstance(response, TransactionResponse):
        return SuccessResponse(message="Transaction initiated", data=response)
    return RedirectResponse(response, status_code=302)
