import paystack
import sentry_sdk
from functools import wraps
from sentry_sdk import logger as sentry_logger
from httpx import Client, Response, HTTPStatusError
from paystack import exceptions as PaystackException


from app.core.config import get_settings

SETTINGS = get_settings()


def handle_paystack_errors(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except PaystackException.ApiKeyError as exc:
            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Configured paystack API Key invalid", extra={"exc": str(exc)}
            )

            raise
        except PaystackException.UnauthorizedException as exc:
            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Unauthorized paystack initialization request", extra={"exc": str(exc)}
            )

            raise
        except PaystackException.ServiceException as exc:
            sentry_sdk.capture_exception(exc)
            sentry_logger.error("Paystack service unavailable", extra={"exc": str(exc)})

            raise

    return wrapper


class PaymentGateway:
    def __init__(self, api_key: str, client: Client = None):
        self._api_key = api_key

        if client:
            self._client = client

    @property
    def api_key(self):
        return self._api_key

    def set_api_key(self):
        paystack.api_key = self._api_key


class Transaction(PaymentGateway):
    @handle_paystack_errors
    def initialize_transaction(
        self, email: str, amount: int, currency: str, channel: str
    ):
        self.set_api_key()

        res = paystack.Transaction.initialize(
            email=email, amount=amount, currency=currency, channels=[channel]
        )
        return res

    @handle_paystack_errors
    def charge_authorization(
        self, email: str, amount: str, currency: str, authorization_code: str
    ):
        self.set_api_key()

        res = paystack.Transaction.charge_authorization(
            email=email,
            amount=amount,
            currency=currency,
            authorization_code=authorization_code,
        )
        return res

    @handle_paystack_errors
    def verify_transaction(self, reference: str):
        self.set_api_key()

        try:
            res = paystack.Transaction.verify(reference=reference)
            return res
        except PaystackException.NotFoundException as exc:
            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Transaction not found with the provided reference",
                extra={"exc": str(exc), "reference": reference},
            )

            raise


class Refund(PaymentGateway):
    @property
    def client(self):
        return self._client

    @handle_paystack_errors
    def request_refund(
        self,
        reference: str,
        amount: int,
        currency: str,
        customer_note: str,
        merchant_note: str,
    ):
        self.set_api_key()

        res = paystack.Refund.create(
            transaction=reference,
            amount=amount,
            currency=currency,
            customer_note=customer_note,
            merchant_note=merchant_note,
        )
        return res

    @handle_paystack_errors
    def get_refund(self, refund_id: int):
        self.set_api_key()

        try:
            res = paystack.Refund.fetch(id=refund_id)
            return res
        except PaystackException.NotFoundException as exc:
            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Refund not found with the provided id",
                extra={"exc": str(exc), "id": refund_id},
            )

            raise

    @handle_paystack_errors
    def retry_refund(
        self, refund_id: int, currency: str, account_number: str, bank_id: str
    ):
        body: dict = {
            "refund_account_details": {
                "currency": currency,
                "account_number": account_number,
                "bank_id": bank_id,
            }
        }
        refund_url: str = f"{SETTINGS.PAYSTACK_RETRY_REFUND_URL}/{refund_id}"

        try:
            res: Response = self._client.post(
                url=refund_url,
                json=body,
                headers={
                    "Authorization": f"Bearer {SETTINGS.PAYSTACK_API_KEY}",
                    "content-type": "application/json",
                },
            )
            return res.json()
        except HTTPStatusError as exc:
            reason = exc.response.json()["message"]
            status_code = exc.response.status_code

            if status_code == 401:
                if (
                    reason == "Invalid key"
                    or reason == "No Authorization Header was found"
                ):
                    raise PaystackException.ApiKeyError(
                        msg=reason
                    )

                raise PaystackException.UnauthorizedException(
                    status=status_code, reason=reason
                )
            if status_code == 404:
                raise PaystackException.NotFoundException(
                    status=status_code, reason=reason
                )
            if status_code >= 500:
                raise PaystackException.ServiceException(
                    status=status_code, reason=reason
                )
            raise
        except Exception as exc:
            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while retrying refund", extra={"refund_id": refund_id}
            )

            raise
