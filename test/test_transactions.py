import httpx
import pytest
import pytest_asyncio
from uuid import uuid7, uuid4
from decimal import Decimal
from sqlalchemy import select
from unittest.mock import patch
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.models.user import User
from app.api.models.wallets import Wallet
from app.api.models.refunds import Refund
from app.api.models.enum import ChannelEnum
from app.api.models.enum import SourceEnum
from app.api.models.enum import RefundStatus
from app.api.models.enum import CurrencyEnum
from app.api.models.enum import TransactionStatus
from app.api.models.transactions import PaymentTransaction
from app.api.models.refund_state_events import RefundStateEvent
from app.api.models.transaction_state_events import TransactionStateEvent


@pytest_asyncio.fixture
async def wallet(
    session_maker: async_sessionmaker[AsyncSession], login: httpx.Response
) -> Wallet:
    async with session_maker() as session:
        user_res = await session.execute(
            select(User).where(User.email == "user@example.com")
        )
        user: User = user_res.scalar_one()

        wallet_res = await session.execute(
            select(Wallet).where(Wallet.user_id == user.id)
        )
        return wallet_res.scalar_one()


@pytest_asyncio.fixture
async def transaction(
    session_maker: async_sessionmaker[AsyncSession], wallet: Wallet
) -> PaymentTransaction:
    async with session_maker() as session:
        transaction = PaymentTransaction(
            id=uuid7(),
            idempotency_key=str(uuid4()),
            user_id=wallet.user_id,
            wallet_id=wallet.id,
            paystack_reference=str(uuid4()),
            amount=Decimal("500.00"),
            channel=ChannelEnum.CARD,
            status=TransactionStatus.SUCCESS,
        )
        session.add(transaction)
        await session.commit()
        await session.refresh(transaction)

        return transaction


@pytest_asyncio.fixture
async def transaction_state(
    session_maker: async_sessionmaker[AsyncSession], transaction: PaymentTransaction
) -> TransactionStateEvent:
    async with session_maker() as session:
        state = TransactionStateEvent(
            id=uuid7(),
            transaction_id=transaction.id,
            status=TransactionStatus.SUCCESS,
            source=SourceEnum.USER_ACTION,
        )
        session.add(state)
        await session.commit()
        await session.refresh(state)

        return state


@pytest_asyncio.fixture
async def refund(
    session_maker: async_sessionmaker[AsyncSession], transaction: PaymentTransaction
) -> Refund:
    async with session_maker() as session:
        refund = Refund(
            id=uuid7(),
            user_id=transaction.user_id,
            payment_transaction_id=transaction.id,
            amount=transaction.amount,
            currency=CurrencyEnum.NGN,
            status=RefundStatus.PROCESSED,
            customer_note="Item arrived damaged",
            merchant_note="Refund approved after review",
            refunded_at=transaction.created_at,
            updated_at=transaction.created_at,
        )
        session.add(refund)
        await session.commit()
        await session.refresh(refund)

        return refund


@pytest_asyncio.fixture
async def refund_needing_attention(
    session_maker: async_sessionmaker[AsyncSession], transaction: PaymentTransaction
) -> Refund:
    async with session_maker() as session:
        refund = Refund(
            id=uuid7(),
            user_id=transaction.user_id,
            payment_transaction_id=transaction.id,
            amount=transaction.amount,
            currency=CurrencyEnum.NGN,
            status=RefundStatus.NEEDS_ATTENTION,
            customer_note="Item arrived damaged",
            merchant_note="Awaiting updated bank account details",
            refunded_at=transaction.created_at,
            updated_at=transaction.created_at,
        )
        session.add(refund)
        await session.commit()
        await session.refresh(refund)

        return refund


@pytest_asyncio.fixture
async def refund_state(
    session_maker: async_sessionmaker[AsyncSession], refund: Refund
) -> RefundStateEvent:
    async with session_maker() as session:
        state = RefundStateEvent(
            id=uuid7(),
            refund_id=refund.id,
            status=RefundStatus.PROCESSED,
            source=SourceEnum.USER_ACTION,
        )
        session.add(state)
        await session.commit()
        await session.refresh(state)

        return state


class TestGetAllTransactions:
    @pytest.mark.asyncio
    async def test_get_all_transactions(
        self,
        async_client: httpx.AsyncClient,
        login: httpx.Response,
        transaction: PaymentTransaction,
    ):
        access_token = login.json()["data"]["access_token"]

        res: httpx.Response = await async_client.get(
            "/transactions",
            headers={
                "Authorization": f"Bearer {access_token}",
                "env": "test",
            },
        )

        json_res = res.json()

        assert res.status_code == 200
        assert json_res["data"][0]["id"] == str(transaction.id)
        assert json_res["data"][0]["wallet_id"] == str(transaction.wallet_id)

    @pytest.mark.asyncio
    async def test_no_transactions(
        self, async_client: httpx.AsyncClient, login: httpx.Response
    ):
        access_token = login.json()["data"]["access_token"]

        res: httpx.Response = await async_client.get(
            "/transactions",
            headers={
                "Authorization": f"Bearer {access_token}",
                "env": "test",
            },
        )

        assert res.status_code == 404

    @pytest.mark.asyncio
    async def test_unauthenticated_get_all_transactions(
        self, async_client: httpx.AsyncClient
    ):
        res: httpx.Response = await async_client.get(
            "/transactions",
            headers={"env": "test"},
        )

        assert res.status_code == 401


class TestGetTransaction:
    @pytest.mark.asyncio
    async def test_get_transaction(
        self,
        async_client: httpx.AsyncClient,
        login: httpx.Response,
        transaction: PaymentTransaction,
    ):
        access_token = login.json()["data"]["access_token"]

        res: httpx.Response = await async_client.get(
            f"/transactions/{transaction.id}",
            headers={
                "Authorization": f"Bearer {access_token}",
                "env": "test",
            },
        )

        json_res = res.json()

        assert res.status_code == 200
        assert json_res["data"]["id"] == str(transaction.id)
        assert json_res["data"]["amount"] == "500.00"
        assert json_res["data"]["status"] == "success"

    @pytest.mark.asyncio
    async def test_transaction_not_found(
        self, async_client: httpx.AsyncClient, login: httpx.Response
    ):
        access_token = login.json()["data"]["access_token"]

        res: httpx.Response = await async_client.get(
            f"/transactions/{uuid4()}",
            headers={
                "Authorization": f"Bearer {access_token}",
                "env": "test",
            },
        )

        assert res.status_code == 404

    @pytest.mark.asyncio
    async def test_unauthenticated_get_transaction(
        self, async_client: httpx.AsyncClient
    ):
        res: httpx.Response = await async_client.get(
            f"/transactions/{uuid4()}",
            headers={"env": "test"},
        )

        assert res.status_code == 401


class TestGetTransactionState:
    @pytest.mark.asyncio
    async def test_get_transaction_state(
        self,
        async_client: httpx.AsyncClient,
        login: httpx.Response,
        transaction_state: TransactionStateEvent,
    ):
        access_token = login.json()["data"]["access_token"]

        res: httpx.Response = await async_client.get(
            f"/transactions/{transaction_state.transaction_id}/events",
            headers={
                "Authorization": f"Bearer {access_token}",
                "env": "test",
            },
        )

        json_res = res.json()

        assert res.status_code == 200
        assert json_res["data"][0]["id"] == str(transaction_state.id)
        assert json_res["data"][0]["status"] == "success"
        assert json_res["data"][0]["source"] == "user_action"

    @pytest.mark.asyncio
    async def test_unauthenticated_get_transaction_state(
        self, async_client: httpx.AsyncClient
    ):
        res: httpx.Response = await async_client.get(
            f"/transactions/{uuid4()}/events",
            headers={"env": "test"},
        )

        assert res.status_code == 401


class TestRequestForRefund:
    @pytest.mark.asyncio
    async def test_request_for_refund(
        self,
        async_client: httpx.AsyncClient,
        login: httpx.Response,
        transaction: PaymentTransaction,
    ):
        access_token = login.json()["data"]["access_token"]

        path: str = "app.api.services.refunds.request_refund.apply_async"

        with patch(path) as task_patch:
            res: httpx.Response = await async_client.post(
                f"/transactions/{transaction.id}/refunds",
                data={"customer_note": "Item arrived damaged"},
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "env": "test",
                },
            )

        task_patch.assert_called_once()

        assert res.status_code == 201

    @pytest.mark.asyncio
    async def test_request_for_refund_transaction_not_found(
        self, async_client: httpx.AsyncClient, login: httpx.Response
    ):
        access_token = login.json()["data"]["access_token"]

        res: httpx.Response = await async_client.post(
            f"/transactions/{uuid4()}/refunds",
            data={"customer_note": "Item arrived damaged"},
            headers={
                "Authorization": f"Bearer {access_token}",
                "env": "test",
            },
        )

        assert res.status_code == 404

    @pytest.mark.asyncio
    async def test_unauthenticated_request_for_refund(
        self, async_client: httpx.AsyncClient
    ):
        res: httpx.Response = await async_client.post(
            f"/transactions/{uuid4()}/refunds",
            data={"customer_note": "Item arrived damaged"},
            headers={"env": "test"},
        )

        assert res.status_code == 401


class TestGetAllRefunds:
    @pytest.mark.asyncio
    async def test_get_all_refunds(
        self, async_client: httpx.AsyncClient, login: httpx.Response, refund: Refund
    ):
        access_token = login.json()["data"]["access_token"]

        res: httpx.Response = await async_client.get(
            "/transactions/refunds",
            headers={
                "Authorization": f"Bearer {access_token}",
                "env": "test",
            },
        )

        json_res = res.json()
        print(json_res)

        assert res.status_code == 200
        assert json_res["data"][0]["id"] == str(refund.id)
        assert json_res["data"][0]["payment_transaction_id"] == str(
            refund.payment_transaction_id
        )

    @pytest.mark.asyncio
    async def test_no_refunds(
        self, async_client: httpx.AsyncClient, login: httpx.Response
    ):
        access_token = login.json()["data"]["access_token"]

        res: httpx.Response = await async_client.get(
            "/transactions/refunds",
            headers={
                "Authorization": f"Bearer {access_token}",
                "env": "test",
            },
        )

        assert res.status_code == 404

    @pytest.mark.asyncio
    async def test_unauthenticated_get_all_refunds(
        self, async_client: httpx.AsyncClient
    ):
        res: httpx.Response = await async_client.get(
            "/transactions/refunds",
            headers={"env": "test"},
        )

        assert res.status_code == 401


class TestGetRefund:
    @pytest.mark.asyncio
    async def test_get_refund(
        self, async_client: httpx.AsyncClient, login: httpx.Response, refund: Refund
    ):
        access_token = login.json()["data"]["access_token"]

        res: httpx.Response = await async_client.get(
            f"/transactions/refunds/{refund.id}",
            headers={
                "Authorization": f"Bearer {access_token}",
                "env": "test",
            },
        )

        json_res = res.json()

        assert res.status_code == 200
        assert json_res["data"]["id"] == str(refund.id)
        assert json_res["data"]["status"] == "processed"

    @pytest.mark.asyncio
    async def test_refund_not_found(
        self, async_client: httpx.AsyncClient, login: httpx.Response
    ):
        access_token = login.json()["data"]["access_token"]

        res: httpx.Response = await async_client.get(
            f"/transactions/refunds/{uuid4()}",
            headers={
                "Authorization": f"Bearer {access_token}",
                "env": "test",
            },
        )

        assert res.status_code == 404

    @pytest.mark.asyncio
    async def test_unauthenticated_get_refund(self, async_client: httpx.AsyncClient):
        res: httpx.Response = await async_client.get(
            f"/transactions/refunds/{uuid4()}",
            headers={"env": "test"},
        )

        assert res.status_code == 401


class TestGetRefundState:
    @pytest.mark.asyncio
    async def test_get_refund_state(
        self,
        async_client: httpx.AsyncClient,
        login: httpx.Response,
        refund_state: RefundStateEvent,
    ):
        access_token = login.json()["data"]["access_token"]

        res: httpx.Response = await async_client.get(
            f"/transactions/refunds/{refund_state.refund_id}/events",
            headers={
                "Authorization": f"Bearer {access_token}",
                "env": "test",
            },
        )

        json_res = res.json()

        assert res.status_code == 200
        assert json_res["data"][0]["id"] == str(refund_state.id)
        assert json_res["data"][0]["status"] == "processed"
        assert json_res["data"][0]["source"] == "user_action"

    @pytest.mark.asyncio
    async def test_unauthenticated_get_refund_state(
        self, async_client: httpx.AsyncClient
    ):
        res: httpx.Response = await async_client.get(
            f"/transactions/refunds/{uuid4()}/events",
            headers={"env": "test"},
        )

        assert res.status_code == 401


class TestRetryRefund:
    @pytest.mark.asyncio
    async def test_retry_refund_recreates_and_enqueues_task(
        self,
        async_client: httpx.AsyncClient,
        login: httpx.Response,
        refund_needing_attention: Refund,
    ):
        access_token = login.json()["data"]["access_token"]

        path: str = "app.api.services.refunds.retry_refund_task.apply_async"
        retry_payload: dict = {"account_number": "0123456789", "bank_id": "044"}

        with patch(path) as task_patch:
            res: httpx.Response = await async_client.post(
                f"/transactions/refunds/{refund_needing_attention.id}/details",
                json=retry_payload,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "env": "test",
                },
            )

        task_patch.assert_called_once()

        assert res.status_code == 201

    @pytest.mark.asyncio
    async def test_retry_refund_wrong_status_not_found(
        self, async_client: httpx.AsyncClient, login: httpx.Response, refund: Refund
    ):
        """`refund` is seeded with status=processed - retry only ever applies
        to a refund whose last attempt is needs_attention, so this 404s."""

        access_token = login.json()["data"]["access_token"]

        retry_payload: dict = {"account_number": "0123456789", "bank_id": "044"}

        res: httpx.Response = await async_client.post(
            f"/transactions/refunds/{refund.id}/details",
            json=retry_payload,
            headers={
                "Authorization": f"Bearer {access_token}",
                "env": "test",
            },
        )

        assert res.status_code == 404

    @pytest.mark.asyncio
    async def test_retry_refund_not_found(
        self, async_client: httpx.AsyncClient, login: httpx.Response
    ):
        access_token = login.json()["data"]["access_token"]

        retry_payload: dict = {"account_number": "0123456789", "bank_id": "044"}

        res: httpx.Response = await async_client.post(
            f"/transactions/refunds/{uuid4()}/details",
            json=retry_payload,
            headers={
                "Authorization": f"Bearer {access_token}",
                "env": "test",
            },
        )

        assert res.status_code == 404

    @pytest.mark.asyncio
    async def test_unauthenticated_retry_refund(self, async_client: httpx.AsyncClient):
        retry_payload: dict = {"account_number": "0123456789", "bank_id": "044"}

        res: httpx.Response = await async_client.post(
            f"/transactions/refunds/{uuid4()}/details",
            json=retry_payload,
            headers={"env": "test"},
        )

        assert res.status_code == 401
