import httpx
import pytest
from uuid import uuid4
from unittest.mock import patch, MagicMock
from paystack import exceptions as PaystackException


from app.core.config import get_settings
from app.api.services.thread_pool import ThreadPool
from app.api.services.payment_gateway import Transaction, Refund

SETTINGS = get_settings()


def transaction_arguments():
    return {"email": "user@example.com", "amount": 500000, "currency": "NGN"}


def refund_arguments():
    return {
        "amount": 500000,
        "currency": "NGN",
        "reference": str(uuid4()),
        "customer_note": "Request a refund for last transaction",
        "merchant_note": "Process user request fro transaction_id 5",
    }


def retry_refund_arguments():
    return {
        "refund_id": 55,
        "currency": "NGN",
        "account_number": str(uuid4()),
        "bank_id": str(uuid4()),
    }


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


def charge_authorization_res():
    return {
        "status": True,
        "message": "Charge attempted",
        "data": {
            "amount": 35247,
            "currency": "NGN",
            "transaction_date": "2024-08-22T10:53:49.000Z",
            "status": "success",
            "reference": "0m7frfnr47ezyxl",
            "domain": "test",
            "metadata": "",
            "gateway_response": "Approved",
            "message": None,
            "channel": "card",
        },
    }


def fetch_transaction_res():
    return {
        "status": True,
        "message": "Transaction retrieved",
        "data": {
            "id": 4099260516,
            "domain": "test",
            "status": "success",
            "reference": "re4lyvq3s3",
            "receipt_number": None,
            "amount": 500000,
            "message": None,
            "gateway_response": "Successful",
            "paid_at": "2024-08-22T09:15:02.000Z",
            "created_at": "2024-08-22T09:14:24.000Z",
            "channel": "card",
            "currency": "NGN",
        },
    }


def verify_transaction_res():
    return {
        "status": True,
        "message": "Verification successful",
        "data": {
            "id": 4099260516,
            "domain": "test",
            "status": "success",
            "reference": "re4lyvq3s3",
            "receipt_number": None,
            "amount": 500000,
            "message": None,
            "gateway_response": "Successful",
            "paid_at": "2024-08-22T09:15:02.000Z",
            "created_at": "2024-08-22T09:14:24.000Z",
            "channel": "card",
            "currency": "NGN",
        },
    }


def request_refund_res():
    return {
        "status": True,
        "message": "Refund has been queued for processing",
        "data": {
            "transaction": {
                "id": 1004723697,
                "domain": "live",
                "reference": "T685312322670591",
                "amount": 500000,
                "paid_at": "2021-08-20T18:34:11.000Z",
                "channel": "apple_pay",
                "currency": "NGN",
                "authorization": {
                    "exp_month": None,
                    "exp_year": None,
                    "account_name": None,
                },
                "customer": {"international_format_phone": None},
                "plan": {},
                "subaccount": {"currency": None},
                "split": {},
                "order_id": None,
                "paidAt": "2021-08-20T18:34:11.000Z",
                "pos_transaction_data": None,
                "source": None,
                "fees_breakdown": None,
            }
        },
    }


def get_refund_res():
    return {
        "status": True,
        "message": "Refund retrieved",
        "data": {
            "integration": 100982,
            "transaction": 1641,
            "dispute": None,
            "settlement": None,
            "domain": "live",
            "amount": 500000,
            "deducted_amount": 500000,
            "fully_deducted": True,
            "currency": "NGN",
            "channel": "migs",
            "status": "processed",
            "refunded_by": "eseyinwale@gmail.com",
            "refunded_at": "2018-01-12T10:54:47.000Z",
            "expected_at": "2017-10-01T21:10:59.000Z",
            "customer_note": "xxx",
            "merchant_note": "xxx",
            "id": 1,
            "createdAt": "2017-09-24T21:10:59.000Z",
            "updatedAt": "2018-01-18T11:59:56.000Z",
        },
    }


def retry_refund_res():
    return {
        "status": True,
        "message": "Refund retried and has been queued for processing",
        "data": {
            "integration": 123456,
            "transaction": 3298598423,
            "dispute": None,
            "settlement": None,
            "id": 1234567,
            "domain": "live",
            "currency": "NGN",
            "amount": 500000,
            "status": "processing",
            "refunded_at": None,
            "expected_at": "2025-10-13T16:02:18.000Z",
            "channel": "isw_3ds",
            "refunded_by": "paystack@email.com",
            "customer_note": "Refund for transaction T708775813895475",
            "merchant_note": "Refund for transaction T708775813895475 by paystack@email.com",
            "deducted_amount": 500000,
            "fully_deducted": True,
            "bank_reference": None,
            "reason": "PROCESSING",
            "customer": None,
            "initiated_by": "paystack@email.com",
            "reversed_at": None,
            "session_id": None,
        },
    }


def make_http_error(status_code: int, message: str = "Error"):
    req = httpx.Request("POST", SETTINGS.PAYSTACK_RETRY_REFUND_URL)
    res = httpx.Response(
        status_code=status_code, request=req, json={"status": False, "message": message}
    )
    return httpx.HTTPStatusError(message=message, request=req, response=res)


@pytest.fixture
def paystack():
    paystack_path = "app.api.services.payment_gateway.paystack"
    with patch(paystack_path) as paystack_mock:
        yield paystack_mock


def mock_client():
    return MagicMock()


class TestTransaction:
    @pytest.fixture(autouse=True)
    def setup_transaction_and_pool(self):
        self.pool = ThreadPool()
        self.transaction = Transaction(api_key=SETTINGS.PAYSTACK_API_KEY)

    @pytest.mark.asyncio
    async def test_initialize_transaction(self, paystack):
        payload: dict = transaction_arguments()
        payload["channel"] = "card"

        response: dict = initialize_transaction_res()

        paystack.Transaction.initialize.return_value = response
        res = await self.pool.run_in_pool(
            self.transaction.initialize_transaction, **payload
        )

        paystack.Transaction.initialize.assert_called_once()

        assert res["status"]
        assert "reference" in res["data"]
        assert res["message"] == response["message"]
        assert res["data"]["reference"] == response["data"]["reference"]
        assert res["data"]["authorization_url"] == response["data"]["authorization_url"]

    @pytest.mark.asyncio
    async def test_initialize_api_key_error(self, paystack):
        payload: dict = transaction_arguments()
        payload["channel"] = "card"

        paystack.Transaction.initialize.side_effect = PaystackException.ApiKeyError(
            "API Key Error"
        )

        with pytest.raises(PaystackException.ApiKeyError):
            await self.pool.run_in_pool(
                self.transaction.initialize_transaction, **payload
            )

        paystack.Transaction.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_unauthorized_error(self, paystack):
        payload: dict = transaction_arguments()
        payload["channel"] = "card"

        paystack.Transaction.initialize.side_effect = (
            PaystackException.UnauthorizedException(status=401)
        )

        with pytest.raises(PaystackException.UnauthorizedException):
            await self.pool.run_in_pool(
                self.transaction.initialize_transaction, **payload
            )

        paystack.Transaction.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_service_error(self, paystack):
        payload: dict = transaction_arguments()
        payload["channel"] = "card"

        paystack.Transaction.initialize.side_effect = (
            PaystackException.ServiceException(status=500)
        )

        with pytest.raises(PaystackException.ServiceException):
            await self.pool.run_in_pool(
                self.transaction.initialize_transaction, **payload
            )

        paystack.Transaction.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_charge_authorization(self, paystack):
        payload: dict = transaction_arguments()
        payload["authorization_code"] = str(uuid4())

        response: dict = charge_authorization_res()

        paystack.Transaction.charge_authorization.return_value = response
        res = await self.pool.run_in_pool(
            self.transaction.charge_authorization, **payload
        )

        paystack.Transaction.charge_authorization.assert_called_once()

        assert res["status"]
        assert "reference" in res["data"]
        assert res["message"] == response["message"]
        assert res["data"]["reference"] == response["data"]["reference"]
        assert res["data"]["gateway_response"] == response["data"]["gateway_response"]

    @pytest.mark.asyncio
    async def test_charge_api_key_error(self, paystack):
        payload: dict = transaction_arguments()
        payload["authorization_code"] = str(uuid4())

        paystack.Transaction.charge_authorization.side_effect = (
            PaystackException.ApiKeyError("API Key Error")
        )

        with pytest.raises(PaystackException.ApiKeyError):
            await self.pool.run_in_pool(
                self.transaction.charge_authorization, **payload
            )

        paystack.Transaction.charge_authorization.assert_called_once()

    @pytest.mark.asyncio
    async def test_charge_unauthorized_error(self, paystack):
        payload: dict = transaction_arguments()
        payload["authorization_code"] = str(uuid4())

        paystack.Transaction.charge_authorization.side_effect = (
            PaystackException.UnauthorizedException(status=401)
        )

        with pytest.raises(PaystackException.UnauthorizedException):
            await self.pool.run_in_pool(
                self.transaction.charge_authorization, **payload
            )

        paystack.Transaction.charge_authorization.assert_called_once()

    @pytest.mark.asyncio
    async def test_charge_service_error(self, paystack):
        payload: dict = transaction_arguments()
        payload["authorization_code"] = str(uuid4())

        paystack.Transaction.charge_authorization.side_effect = (
            PaystackException.ServiceException(status=500)
        )

        with pytest.raises(PaystackException.ServiceException):
            await self.pool.run_in_pool(
                self.transaction.charge_authorization, **payload
            )

        paystack.Transaction.charge_authorization.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_transaction(self, paystack):
        transaction_id = 4099260516
        response: dict = fetch_transaction_res()

        paystack.Transaction.fetch.return_value = response
        res = await self.pool.run_in_pool(
            self.transaction.fetch_transaction, id=transaction_id
        )

        paystack.Transaction.fetch.assert_called_once()

        assert res["status"]
        assert "reference" in res["data"]
        assert res["message"] == response["message"]
        assert res["data"]["reference"] == response["data"]["reference"]
        assert res["data"]["gateway_response"] == response["data"]["gateway_response"]

    @pytest.mark.asyncio
    async def test_fetch_not_found_error(self, paystack):
        transaction_id = 4099260516

        paystack.Transaction.fetch.side_effect = PaystackException.NotFoundException(
            status=404
        )

        with pytest.raises(PaystackException.NotFoundException):
            await self.pool.run_in_pool(
                self.transaction.fetch_transaction, id=transaction_id
            )

        paystack.Transaction.fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_api_key_error(self, paystack):
        transaction_id = 4099260516

        paystack.Transaction.fetch.side_effect = PaystackException.ApiKeyError(
            "API Key Error"
        )

        with pytest.raises(PaystackException.ApiKeyError):
            await self.pool.run_in_pool(
                self.transaction.fetch_transaction, id=transaction_id
            )

        paystack.Transaction.fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_unauthorized_error(self, paystack):
        transaction_id = 4099260516

        paystack.Transaction.fetch.side_effect = (
            PaystackException.UnauthorizedException(status=401)
        )

        with pytest.raises(PaystackException.UnauthorizedException):
            await self.pool.run_in_pool(
                self.transaction.fetch_transaction, id=transaction_id
            )

        paystack.Transaction.fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_service_error(self, paystack):
        transaction_id = 4099260516

        paystack.Transaction.fetch.side_effect = PaystackException.ServiceException(
            status=500
        )

        with pytest.raises(PaystackException.ServiceException):
            await self.pool.run_in_pool(
                self.transaction.fetch_transaction, id=transaction_id
            )

        paystack.Transaction.fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_verify_transaction(self, paystack):
        reference = str(uuid4())
        response: dict = verify_transaction_res()

        paystack.Transaction.verify.return_value = response
        res = await self.pool.run_in_pool(
            self.transaction.verify_transaction, reference=reference
        )

        paystack.Transaction.verify.assert_called_once()

        assert res["status"]
        assert "reference" in res["data"]
        assert res["message"] == response["message"]
        assert res["data"]["reference"] == response["data"]["reference"]
        assert res["data"]["gateway_response"] == response["data"]["gateway_response"]

    @pytest.mark.asyncio
    async def test_verify_not_found_error(self, paystack):
        reference = str(uuid4())

        paystack.Transaction.verify.side_effect = PaystackException.NotFoundException(
            status=404
        )

        with pytest.raises(PaystackException.NotFoundException):
            await self.pool.run_in_pool(
                self.transaction.verify_transaction, reference=reference
            )

        paystack.Transaction.verify.assert_called_once()

    @pytest.mark.asyncio
    async def test_verify_api_key_error(self, paystack):
        reference = str(uuid4())

        paystack.Transaction.verify.side_effect = PaystackException.ApiKeyError(
            "API Key Error"
        )

        with pytest.raises(PaystackException.ApiKeyError):
            await self.pool.run_in_pool(
                self.transaction.verify_transaction, reference=reference
            )

        paystack.Transaction.verify.assert_called_once()

    @pytest.mark.asyncio
    async def test_verify_unauthorized_error(self, paystack):
        reference = str(uuid4())

        paystack.Transaction.verify.side_effect = (
            PaystackException.UnauthorizedException(status=401)
        )

        with pytest.raises(PaystackException.UnauthorizedException):
            await self.pool.run_in_pool(
                self.transaction.verify_transaction, reference=reference
            )

        paystack.Transaction.verify.assert_called_once()

    @pytest.mark.asyncio
    async def test_verify_service_error(self, paystack):
        reference = str(uuid4())

        paystack.Transaction.verify.side_effect = PaystackException.ServiceException(
            status=500
        )

        with pytest.raises(PaystackException.ServiceException):
            await self.pool.run_in_pool(
                self.transaction.verify_transaction, reference=reference
            )

        paystack.Transaction.verify.assert_called_once()


class TestRefund:
    @pytest.fixture(autouse=True)
    def setup_transaction_and_pool(self):
        self.pool = ThreadPool()
        self.refund = Refund(api_key=SETTINGS.PAYSTACK_API_KEY, client=mock_client())

    @pytest.mark.asyncio
    async def test_request_refund(self, paystack):
        payload: dict = refund_arguments()
        response: dict = request_refund_res()

        paystack.Refund.create.return_value = response
        res = await self.pool.run_in_pool(self.refund.request_refund, **payload)

        paystack.Refund.create.assert_called_once()

        assert res["status"]
        assert res["message"] == response["message"]
        assert "reference" in res["data"]["transaction"]
        assert (
            res["data"]["transaction"]["reference"]
            == response["data"]["transaction"]["reference"]
        )

    @pytest.mark.asyncio
    async def test_request_refund_api_key_error(self, paystack):
        payload: dict = refund_arguments()

        paystack.Refund.create.side_effect = PaystackException.ApiKeyError(
            "API Key Error"
        )

        with pytest.raises(PaystackException.ApiKeyError):
            await self.pool.run_in_pool(self.refund.request_refund, **payload)

        paystack.Refund.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_refund_unauthorized_error(self, paystack):
        payload: dict = refund_arguments()

        paystack.Refund.create.side_effect = PaystackException.UnauthorizedException(
            status=401
        )

        with pytest.raises(PaystackException.UnauthorizedException):
            await self.pool.run_in_pool(self.refund.request_refund, **payload)

        paystack.Refund.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_refund_service_error(self, paystack):
        payload: dict = refund_arguments()

        paystack.Refund.create.side_effect = PaystackException.ServiceException(
            status=500
        )

        with pytest.raises(PaystackException.ServiceException):
            await self.pool.run_in_pool(self.refund.request_refund, **payload)

        paystack.Refund.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_refund(self, paystack):
        refund_id = 55
        response: dict = get_refund_res()

        paystack.Refund.fetch.return_value = response
        res = await self.pool.run_in_pool(self.refund.get_refund, refund_id=refund_id)

        paystack.Refund.fetch.assert_called_once()

        assert res["status"]
        assert res["message"] == response["message"]
        assert response["data"]["status"] == "processed"

    @pytest.mark.asyncio
    async def test_get_refund_api_key_error(self, paystack):
        refund_id = 55

        paystack.Refund.fetch.side_effect = PaystackException.ApiKeyError(
            "API Key Error"
        )

        with pytest.raises(PaystackException.ApiKeyError):
            await self.pool.run_in_pool(self.refund.get_refund, refund_id=refund_id)

        paystack.Refund.fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_refund_unauthorized_error(self, paystack):
        refund_id = 55

        paystack.Refund.fetch.side_effect = PaystackException.UnauthorizedException(
            status=401
        )

        with pytest.raises(PaystackException.UnauthorizedException):
            await self.pool.run_in_pool(self.refund.get_refund, refund_id=refund_id)

        paystack.Refund.fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_refund_service_error(self, paystack):
        refund_id = 55

        paystack.Refund.fetch.side_effect = PaystackException.ServiceException(
            status=500
        )

        with pytest.raises(PaystackException.ServiceException):
            await self.pool.run_in_pool(self.refund.get_refund, refund_id=refund_id)

        paystack.Refund.fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_refund(self):
        response: dict = retry_refund_res()
        payload: dict = retry_refund_arguments()

        client = self.refund.client
        client.post.return_value = httpx.Response(status_code=201, json=response)

        res = await self.pool.run_in_pool(self.refund.retry_refund, **payload)

        client.post.assert_called_once()

        assert res["status"]
        assert res["message"] == response["message"]
        assert res["data"]["status"] in response["data"]["status"]

    @pytest.mark.asyncio
    async def test_retry_api_key_error(self):
        payload: dict = retry_refund_arguments()

        client = self.refund.client
        client.post.side_effect = make_http_error(401, "No Authorization Header was found")

        with pytest.raises(PaystackException.ApiKeyError):
            await self.pool.run_in_pool(self.refund.retry_refund, **payload)

        client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_unauthorized_error(self):
        payload: dict = retry_refund_arguments()

        client = self.refund.client
        client.post.side_effect = make_http_error(401, "Unauthorized error")

        with pytest.raises(PaystackException.UnauthorizedException):
            await self.pool.run_in_pool(self.refund.retry_refund, **payload)

        client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_service_error(self):
        payload: dict = retry_refund_arguments()

        client = self.refund.client
        client.post.side_effect = make_http_error(500, "Service error")

        with pytest.raises(PaystackException.ServiceException):
            await self.pool.run_in_pool(self.refund.retry_refund, **payload)

        client.post.assert_called_once()
