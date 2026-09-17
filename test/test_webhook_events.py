import httpx
import pytest
from unittest.mock import patch, AsyncMock, MagicMock


from app.main import app
from app.deps import get_security
from app.core.security import Security


def charge_success_payload() -> dict:
    return {
        "event": "charge.success",
        "data": {
            "id": 4099260516,
            "reference": "re4lyvq3s3",
            "amount": 500000,
            "currency": "NGN",
            "channel": "card",
            "gateway_response": "Successful",
            "authorization": {
                "authorization_code": "AUTH_abc123",
                "card_type": "visa",
                "country_code": "NG",
                "reusable": True,
                "exp_month": "12",
                "exp_year": "2030",
            },
        },
    }


def get_security_mock(signature_valid: bool = True) -> Security:
    security = MagicMock(spec=Security())
    security.verify_webhook_signature = AsyncMock(return_value=signature_valid)

    return security


class TestReceiveWebhookEvents:
    @pytest.mark.asyncio
    async def test_receive_charge_success_event(
        self, async_client: httpx.AsyncClient
    ):
        app.dependency_overrides[get_security] = lambda: get_security_mock(True)

        path: str = (
            "app.api.services.webhook_events.process_webhook_events.apply_async"
        )

        with patch(path) as task_patch:
            res: httpx.Response = await async_client.post(
                "/webhooks/paystack",
                json=charge_success_payload(),
                headers={
                    "x-paystack-signature": "test-signature",
                    "env": "test",
                },
            )

        task_patch.assert_called_once()

        assert res.status_code == 200

    @pytest.mark.asyncio
    async def test_receive_event_invalid_signature(
        self, async_client: httpx.AsyncClient
    ):
        app.dependency_overrides[get_security] = lambda: get_security_mock(False)

        path: str = (
            "app.api.services.webhook_events.process_webhook_events.apply_async"
        )

        with patch(path) as task_patch:
            res: httpx.Response = await async_client.post(
                "/webhooks/paystack",
                json=charge_success_payload(),
                headers={
                    "x-paystack-signature": "invalid-signature",
                    "env": "test",
                },
            )

        task_patch.assert_not_called()

        assert res.status_code == 200
