import httpx
import pytest
import pytest_asyncio
from uuid import uuid7, uuid4
from decimal import Decimal
from sqlalchemy import select
from redis.asyncio import Redis
from unittest.mock import patch
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.models.user import User
from app.api.models.wallets import Wallet
from app.api.models.enum import ChannelEnum
from app.api.models.enum import TransactionStatus
from app.api.models.wallet_credits import WalletCredit
from app.api.models.transactions import PaymentTransaction


def initialize_transaction_res():
    return {
        "status": True,
        "message": "Authorization URL created",
        "data": {
            "authorization_url": "https://checkout.paystack.com/3ni8kdavz62431k",
            "access_code": "3ni8kdavz62431k",
            "reference": "re4lyvq3s3",
        },
    }


@pytest.fixture
def paystack():
    paystack_path = "app.api.services.payment_gateway.paystack"
    with patch(paystack_path) as paystack_mock:
        yield paystack_mock


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
async def wallet_credit(
    session_maker: async_sessionmaker[AsyncSession], wallet: Wallet
) -> WalletCredit:
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
            wallet_credited=True,
        )
        session.add(transaction)
        await session.flush()

        credit = WalletCredit(
            id=uuid7(),
            wallet_id=wallet.id,
            payment_transaction_id=transaction.id,
            amount=Decimal("500.00"),
        )
        session.add(credit)
        await session.commit()
        await session.refresh(credit)

        return credit


@pytest_asyncio.fixture
async def pending_transaction(
    session_maker: async_sessionmaker[AsyncSession], wallet: Wallet
) -> PaymentTransaction:
    async with session_maker() as session:
        transaction = PaymentTransaction(
            id=uuid7(),
            idempotency_key=str(uuid4()),
            user_id=wallet.user_id,
            wallet_id=wallet.id,
            paystack_reference=str(uuid4()),
            amount=Decimal("1000.00"),
            channel=ChannelEnum.CARD,
            status=TransactionStatus.PENDING,
        )
        session.add(transaction)
        await session.commit()
        await session.refresh(transaction)

        return transaction


@pytest_asyncio.fixture
async def open_circuit(async_client: httpx.AsyncClient, test_redis_client: Redis):
    retry_at: str = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()

    await test_redis_client.hset(
        "paystack:circuit",
        mapping={
            "failures": 5,
            "state": "open",
            "retry_at": retry_at,
            "half_open_requests": 0,
        },
    )


class TestGetWallet:
    @pytest.mark.asyncio
    async def test_get_wallet(
        self, async_client: httpx.AsyncClient, login: httpx.Response, wallet: Wallet
    ):
        access_token = login.json()["data"]["access_token"]

        res: httpx.Response = await async_client.get(
            "/wallets/me",
            headers={
                "Authorization": f"Bearer {access_token}",
                "env": "test",
            },
        )

        json_res = res.json()

        assert res.status_code == 200
        assert json_res["data"]["id"] == str(wallet.id)
        assert json_res["data"]["user_id"] == str(wallet.user_id)
        assert json_res["data"]["balance"] == "0.00"
        assert json_res["data"]["currency"] == "NGN"

    @pytest.mark.asyncio
    async def test_unauthenticated_get_wallet(self, async_client: httpx.AsyncClient):
        res: httpx.Response = await async_client.get(
            "/wallets/me",
            headers={"env": "test"},
        )

        assert res.status_code == 401


class TestGetWalletCredits:
    @pytest.mark.asyncio
    async def test_get_wallet_credits(
        self,
        async_client: httpx.AsyncClient,
        login: httpx.Response,
        wallet_credit: WalletCredit,
    ):
        access_token = login.json()["data"]["access_token"]

        res: httpx.Response = await async_client.get(
            "/wallets/me/credits",
            headers={
                "Authorization": f"Bearer {access_token}",
                "env": "test",
            },
        )

        json_res = res.json()

        assert res.status_code == 200
        assert json_res["cursor"] is None
        assert json_res["data"][0]["id"] == str(wallet_credit.id)
        assert json_res["data"][0]["wallet_id"] == str(wallet_credit.wallet_id)

    @pytest.mark.asyncio
    async def test_no_wallet_credits(
        self, async_client: httpx.AsyncClient, login: httpx.Response, wallet: Wallet
    ):
        access_token = login.json()["data"]["access_token"]

        res: httpx.Response = await async_client.get(
            "/wallets/me/credits",
            headers={
                "Authorization": f"Bearer {access_token}",
                "env": "test",
            },
        )

        assert res.status_code == 404

    @pytest.mark.asyncio
    async def test_unauthenticated_get_wallet_credits(
        self, async_client: httpx.AsyncClient
    ):
        res: httpx.Response = await async_client.get(
            "/wallets/me/credits",
            headers={"env": "test"},
        )

        assert res.status_code == 401


class TestGetWalletCredit:
    @pytest.mark.asyncio
    async def test_get_wallet_credit(
        self,
        async_client: httpx.AsyncClient,
        login: httpx.Response,
        wallet_credit: WalletCredit,
    ):
        access_token = login.json()["data"]["access_token"]

        res: httpx.Response = await async_client.get(
            f"/wallets/me/credits/{wallet_credit.id}",
            headers={
                "Authorization": f"Bearer {access_token}",
                "env": "test",
            },
        )

        json_res = res.json()

        assert res.status_code == 200
        assert json_res["data"]["id"] == str(wallet_credit.id)
        assert json_res["data"]["amount"] == "500.00"

    @pytest.mark.asyncio
    async def test_wallet_credit_not_found(
        self, async_client: httpx.AsyncClient, login: httpx.Response, wallet: Wallet
    ):
        access_token = login.json()["data"]["access_token"]

        res: httpx.Response = await async_client.get(
            f"/wallets/me/credits/{uuid4()}",
            headers={
                "Authorization": f"Bearer {access_token}",
                "env": "test",
            },
        )

        assert res.status_code == 404

    @pytest.mark.asyncio
    async def test_unauthenticated_get_wallet_credit(
        self, async_client: httpx.AsyncClient
    ):
        res: httpx.Response = await async_client.get(
            f"/wallets/me/credits/{uuid4()}",
            headers={"env": "test"},
        )

        assert res.status_code == 401


class TestWalletFundCallback:
    @pytest.mark.asyncio
    async def test_wallet_fund_callback(
        self,
        async_client: httpx.AsyncClient,
        login: httpx.Response,
        pending_transaction: PaymentTransaction,
    ):
        access_token = login.json()["data"]["access_token"]

        res: httpx.Response = await async_client.get(
            "/wallets/fund/callback",
            params={"reference": pending_transaction.paystack_reference},
            headers={
                "Authorization": f"Bearer {access_token}",
                "env": "test",
            },
        )

        json_res = res.json()

        assert res.status_code == 200
        assert json_res["data"]["id"] == str(pending_transaction.id)
        assert (
            json_res["data"]["paystack_reference"]
            == pending_transaction.paystack_reference
        )

    @pytest.mark.asyncio
    async def test_unauthenticated_wallet_fund_callback(
        self, async_client: httpx.AsyncClient
    ):
        res: httpx.Response = await async_client.get(
            "/wallets/fund/callback",
            params={"reference": str(uuid4())},
            headers={"env": "test"},
        )

        assert res.status_code == 401


class TestFundWallet:
    @pytest.mark.asyncio
    async def test_fund_wallet_initializes_transaction(
        self,
        async_client: httpx.AsyncClient,
        login: httpx.Response,
        wallet: Wallet,
        paystack,
    ):
        access_token = login.json()["data"]["access_token"]
        response: dict = initialize_transaction_res()

        paystack.Transaction.initialize.return_value = response

        fund_payload: dict = {"channel": "card", "amount": "500.00"}

        res: httpx.Response = await async_client.post(
            "/wallets/me/fund",
            json=fund_payload,
            headers={
                "Authorization": f"Bearer {access_token}",
                "x-idempotency-key": str(uuid4()),
                "env": "test",
            },
        )

        paystack.Transaction.initialize.assert_called_once()

        assert res.status_code == 302
        assert res.headers["location"] == response["data"]["authorization_url"]

    @pytest.mark.asyncio
    async def test_fund_wallet_returns_existing_transaction_for_idempotency_key(
        self,
        async_client: httpx.AsyncClient,
        login: httpx.Response,
        pending_transaction: PaymentTransaction,
        paystack,
    ):
        access_token = login.json()["data"]["access_token"]

        fund_payload: dict = {
            "channel": pending_transaction.channel.value,
            "amount": str(pending_transaction.amount),
        }

        res: httpx.Response = await async_client.post(
            "/wallets/me/fund",
            json=fund_payload,
            headers={
                "Authorization": f"Bearer {access_token}",
                "x-idempotency-key": pending_transaction.idempotency_key,
                "env": "test",
            },
        )

        json_res = res.json()

        paystack.Transaction.initialize.assert_not_called()

        assert res.status_code == 201
        assert json_res["data"]["id"] == str(pending_transaction.id)

    @pytest.mark.asyncio
    async def test_fund_wallet_service_unavailable_when_circuit_open(
        self,
        async_client: httpx.AsyncClient,
        login: httpx.Response,
        wallet: Wallet,
        open_circuit,
        paystack,
    ):
        access_token = login.json()["data"]["access_token"]

        fund_payload: dict = {"channel": "card", "amount": "500.00"}

        res: httpx.Response = await async_client.post(
            "/wallets/me/fund",
            json=fund_payload,
            headers={
                "Authorization": f"Bearer {access_token}",
                "x-idempotency-key": str(uuid4()),
                "env": "test",
            },
        )

        paystack.Transaction.initialize.assert_not_called()

        assert res.status_code == 503

    @pytest.mark.asyncio
    async def test_invalid_channel_fund_wallet(
        self, async_client: httpx.AsyncClient, login: httpx.Response
    ):
        access_token = login.json()["data"]["access_token"]

        fund_payload: dict = {"channel": "paypal", "amount": "500.00"}

        res: httpx.Response = await async_client.post(
            "/wallets/me/fund",
            json=fund_payload,
            headers={
                "Authorization": f"Bearer {access_token}",
                "x-idempotency-key": str(uuid4()),
                "env": "test",
            },
        )

        assert res.status_code == 422

    @pytest.mark.asyncio
    async def test_unauthenticated_fund_wallet(self, async_client: httpx.AsyncClient):
        fund_payload: dict = {"channel": "card", "amount": "500.00"}

        res: httpx.Response = await async_client.post(
            "/wallets/me/fund",
            json=fund_payload,
            headers={"env": "test"},
        )

        assert res.status_code == 401
