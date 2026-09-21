import asyncio
import httpx
import pytest
import pytest_asyncio
from uuid import uuid4, uuid7
from decimal import Decimal
from paystack import exceptions as PaystackException
from unittest.mock import patch
from asgi_lifespan import LifespanManager
from sqlalchemy import select, create_engine
from sqlalchemy.orm import sessionmaker as sync_sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, AsyncEngine

from app.main import app
from app.deps import get_redis_client
from app.core.config import get_settings
from app.core.security import Security
from app.database.session import get_session
from app.api.models.user import User
from app.api.models.wallets import Wallet
from app.api.models.enum import ChannelEnum, TransactionStatus
from app.api.models.wallet_credits import WalletCredit
from app.api.models.transactions import PaymentTransaction
from app.api.services.circuit_breaker import CircuitBreaker
from app.worker.services.webhooks import TaskWebhook

from test.test_wallets import mock_paystack_response, wallet, paystack

TEST_PASSWORD = "test_password123"


def unique_initialize_transaction_res() -> dict:
    """Real-commit tests (real_commit_client) persist for real, unlike the
    rollback-isolated ones - reusing test_wallets.py's fixed reference
    across more than one of them collides on payment_transactions'
    paystack_reference unique constraint. Each caller needs its own."""
    reference = str(uuid4())
    return {
        "status": True,
        "message": "Authorization URL created",
        "data": {
            "authorization_url": f"https://checkout.paystack.com/{reference}",
            "access_code": reference,
            "reference": reference,
        },
    }


def _sync_test_engine():
    """A plain sync engine against the same physical test database the
    async fixtures create/drop - needed to exercise worker-side (sync
    session) code directly, since Celery tasks never run sync in tests."""
    sync_url = get_settings().ASYNC_TEST_DB_URL.replace(
        "postgresql+asyncpg", "postgresql+psycopg2"
    )
    return create_engine(sync_url)


@pytest_asyncio.fixture
async def real_commit_client(async_engine: AsyncEngine, test_redis_client):
    maker = async_sessionmaker(
        bind=async_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def get_test_session():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    app.dependency_overrides[get_redis_client] = lambda: test_redis_client

    async with LifespanManager(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://localhost/api/v1"
        ) as client:
            yield client

    app.dependency_overrides.clear()


async def create_and_login_user(client: httpx.AsyncClient, email: str) -> tuple:
    """Bypasses the OTP/email signup flow entirely - inserts an
    already-verified user + empty wallet directly (same trick
    test_wallets.py's own fixtures use for a ready-made row), then logs
    in for real to get a working access token."""
    security = Security()
    hashed = await security.hash_password(TEST_PASSWORD)

    engine = _sync_test_engine()
    Session = sync_sessionmaker(bind=engine)
    with Session() as session:
        user = User(
            id=uuid7(),
            type="email",
            first_name="test",
            last_name="user",
            email=email,
            hashed_password=hashed,
            is_active=True,
            is_verified=True,
        )
        session.add(user)
        session.flush()

        wallet = Wallet(id=uuid7(), user_id=user.id, balance=Decimal("0"))
        session.add(wallet)
        session.commit()

        user_id, wallet_id = user.id, wallet.id
    engine.dispose()

    res = await client.post(
        "/auth/login",
        json={"email": email, "password": TEST_PASSWORD},
        headers={"env": "test"},
    )
    token = res.json()["data"]["access_token"]
    return token, user_id, wallet_id


class TestConcurrentDuplicateFundRequest:
    """The insert-and-compare fix in fund_wallet exists specifically to
    guarantee this: two requests racing on the same idempotency_key must
    still only ever call Paystack once, because Postgres blocks the
    second INSERT...ON CONFLICT until the first's transaction resolves."""

    @pytest.mark.asyncio
    async def test_concurrent_duplicate_request_calls_paystack_once(
        self, real_commit_client: httpx.AsyncClient
    ):
        token, _, _ = await create_and_login_user(
            real_commit_client, f"concurrent-{uuid4()}@example.com"
        )

        response = unique_initialize_transaction_res()
        idempotency_key = str(uuid4())
        fund_payload = {"channel": "card", "amount": "500.00"}
        headers = {
            "Authorization": f"Bearer {token}",
            "x-idempotency-key": idempotency_key,
            "env": "test",
        }

        with patch("app.api.services.payment_gateway.paystack") as paystack_mock:
            paystack_mock.Transaction.initialize.return_value = mock_paystack_response(
                response
            )

            results = await asyncio.gather(
                real_commit_client.post(
                    "/wallets/me/fund", json=fund_payload, headers=headers
                ),
                real_commit_client.post(
                    "/wallets/me/fund", json=fund_payload, headers=headers
                ),
            )

        paystack_mock.Transaction.initialize.assert_called_once()

        for res in results:
            assert res.status_code == 302
            assert res.headers["location"] == response["data"]["authorization_url"]


class TestSequentialDuplicateFundRequest:
    @pytest.mark.asyncio
    async def test_second_real_request_does_not_call_paystack_again(
        self, real_commit_client: httpx.AsyncClient
    ):
        token, _, _ = await create_and_login_user(
            real_commit_client, f"sequential-{uuid4()}@example.com"
        )

        response = unique_initialize_transaction_res()
        idempotency_key = str(uuid4())
        fund_payload = {"channel": "card", "amount": "500.00"}
        headers = {
            "Authorization": f"Bearer {token}",
            "x-idempotency-key": idempotency_key,
            "env": "test",
        }

        with patch("app.api.services.payment_gateway.paystack") as paystack_mock:
            paystack_mock.Transaction.initialize.return_value = mock_paystack_response(
                response
            )

            first = await real_commit_client.post(
                "/wallets/me/fund", json=fund_payload, headers=headers
            )
            second = await real_commit_client.post(
                "/wallets/me/fund", json=fund_payload, headers=headers
            )

        paystack_mock.Transaction.initialize.assert_called_once()
        assert first.status_code == 302
        assert second.status_code == 302
        assert first.headers["location"] == second.headers["location"]


class TestCircuitBreakerTripsFromRealFailures:
    """test_fund_wallet_service_unavailable_when_circuit_open (test_wallets.py)
    covers "given an already-open circuit, reject" via a pre-seeded redis
    hash. This covers the other half: repeated real failures must actually
    drive the breaker open in the first place."""

    @pytest.mark.asyncio
    async def test_repeated_paystack_failures_trip_circuit_open(
        self, async_client: httpx.AsyncClient, login: httpx.Response, wallet, paystack
    ):
        access_token = login.json()["data"]["access_token"]
        paystack.Transaction.initialize.side_effect = (
            PaystackException.ServiceException(status=503, reason="Service Unavailable")
        )

        for _ in range(CircuitBreaker.FAILURE_THRESHOLD):
            res = await async_client.post(
                "/wallets/me/fund",
                json={"channel": "card", "amount": "500.00"},
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "x-idempotency-key": str(uuid4()),
                    "env": "test",
                },
            )
            assert res.status_code == 503

        # the breaker should now be open - the next attempt is rejected
        # without ever touching paystack again
        paystack.Transaction.initialize.reset_mock()
        paystack.Transaction.initialize.side_effect = (
            PaystackException.ServiceException(status=503, reason="Service Unavailable")
        )

        res = await async_client.post(
            "/wallets/me/fund",
            json={"channel": "card", "amount": "500.00"},
            headers={
                "Authorization": f"Bearer {access_token}",
                "x-idempotency-key": str(uuid4()),
                "env": "test",
            },
        )

        assert res.status_code == 503
        paystack.Transaction.initialize.assert_not_called()


class TestDuplicateWebhookDoesNotDoubleCredit:
    """Router-level dedup (webhook_events unique index) stops a second
    identical POST from even dispatching a task. This covers the deeper,
    independent guard: even if TaskWebhook.transaction_success_event ran
    twice for the same transaction, the wallet must only be credited once."""

    def test_duplicate_charge_success_event_credits_wallet_once(self):
        engine = _sync_test_engine()
        Session = sync_sessionmaker(bind=engine)

        with Session() as session:
            user = User(
                id=uuid7(),
                type="email",
                first_name="test",
                last_name="user",
                email=f"dup-webhook-{uuid4()}@example.com",
                hashed_password="unused",
                is_active=True,
                is_verified=True,
            )
            session.add(user)
            session.flush()

            wallet = Wallet(id=uuid7(), user_id=user.id, balance=Decimal("0"))
            session.add(wallet)
            session.flush()

            reference = str(uuid4())
            transaction = PaymentTransaction(
                id=uuid7(),
                idempotency_key=str(uuid4()),
                user_id=user.id,
                wallet_id=wallet.id,
                paystack_reference=reference,
                amount=Decimal("500.00"),
                channel=ChannelEnum.BANK_TRANSFER,
                status=TransactionStatus.PENDING,
            )
            session.add(transaction)
            session.commit()

            payload = {
                "reference": reference,
                "gateway_response": "Successful",
                "expiry_year": "2030",
                "expiry_month": "12",
            }

            task_webhook = TaskWebhook("test-task", session)

            task_webhook.transaction_success_event(payload)
            session.commit()

            # the exact same event, arriving again
            task_webhook.transaction_success_event(payload)
            session.commit()

            session.refresh(wallet)
            assert wallet.balance == Decimal("500.00")

            credits = (
                session.execute(
                    select(WalletCredit).where(
                        WalletCredit.payment_transaction_id == transaction.id
                    )
                )
                .scalars()
                .all()
            )
            assert len(credits) == 1
        engine.dispose()


class TestBankTransferRejectedDoesNotCreditWallet:
    def test_bank_transfer_rejected_event_leaves_wallet_untouched(self):
        engine = _sync_test_engine()
        Session = sync_sessionmaker(bind=engine)

        with Session() as session:
            user = User(
                id=uuid7(),
                type="email",
                first_name="test",
                last_name="user",
                email=f"reject-{uuid4()}@example.com",
                hashed_password="unused",
                is_active=True,
                is_verified=True,
            )
            session.add(user)
            session.flush()

            wallet = Wallet(id=uuid7(), user_id=user.id, balance=Decimal("0"))
            session.add(wallet)
            session.flush()

            reference = str(uuid4())
            transaction = PaymentTransaction(
                id=uuid7(),
                idempotency_key=str(uuid4()),
                user_id=user.id,
                wallet_id=wallet.id,
                paystack_reference=reference,
                amount=Decimal("500.00"),
                channel=ChannelEnum.BANK_TRANSFER,
                status=TransactionStatus.PENDING,
            )
            session.add(transaction)
            session.commit()

            task_webhook = TaskWebhook("test-task", session)

            with patch(
                "app.api.services.payment_gateway.paystack"
            ) as paystack_mock:
                paystack_mock.Transaction.fetch.return_value = mock_paystack_response(
                    {"data": {"reference": reference}}
                )
                task_webhook.transfer_reject_event({"transaction_id": 12345})
            session.commit()

            session.refresh(wallet)
            session.refresh(transaction)

            assert wallet.balance == Decimal("0")
            assert transaction.status == TransactionStatus.REJECTED
        engine.dispose()
