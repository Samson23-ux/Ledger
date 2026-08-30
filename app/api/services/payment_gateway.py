import paystack
import sentry_sdk
from functools import wraps
from sentry_sdk import logger as sentry_logger
from paystack import exceptions as PaystackException


from app.core.exceptions import ServerError, ServiceUnavailable, ReferenceNotFound


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

            raise ServerError() from exc
        except PaystackException.UnauthorizedException as exc:
            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Unauthorized paystack initialization request", extra={"exc": str(exc)}
            )

            raise ServerError() from exc
        except PaystackException.ServiceException as exc:
            sentry_sdk.capture_exception(exc)
            sentry_logger.error("Paystack service unavailable", extra={"exc": str(exc)})

            raise ServiceUnavailable() from exc

    return wrapper


class PaymentGateway:
    def __init__(self, api_key: str, gateway: paystack):
        self._api_key = api_key
        self._gateway = gateway

    @property
    def api_key(self):
        return self._api_key

    def set_api_key(self):
        self._gateway.api_key = self._api_key


class Transaction(PaymentGateway):
    @handle_paystack_errors
    def initialize_transaction(
        self, email: str, amount: int, currency: str, channel: str
    ):
        self.set_api_key()

        res = self._gateway.Transaction.initialize(
            email=email, amount=amount, currency=currency, channels=[channel]
        )
        return res

    @handle_paystack_errors
    def charge_authorization(
        self, email: str, amount: str, currency: str, authorization_code: str
    ):
        self.set_api_key()

        res = self._gateway.Transaction.charge_authorization(
            email=email,
            amount=amount,
            currency=currency,
            authorization_code=authorization_code,
        )
        return res

    @handle_paystack_errors
    def check_authorization(
        self, email: str, amount: str, currency: str, authorization_code: str
    ):
        self.set_api_key()

        res = self._gateway.Transaction.check_authorization(
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
            res = self._gateway.Transaction.verify(reference=reference)
            return res
        except PaystackException.NotFoundException as exc:
            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Transaction not found with the provided reference",
                extra={"exc": str(exc), "reference": reference},
            )

            raise ReferenceNotFound() from exc


class Refund(PaymentGateway):
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

        res = self._gateway.Refund.create(
            transaction=reference,
            amount=amount,
            currency=currency,
            customer_note=customer_note,
            merchant_note=merchant_note,
        )
        return res

    @handle_paystack_errors
    def get_refund(self, refund_id: str):
        self.set_api_key()

        try:
            res = self._gateway.Refund.fetch(id=refund_id)
            return res
        except PaystackException.NotFoundException as exc:
            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Refund not found with the provided id",
                extra={"exc": str(exc), "id": refund_id},
            )

            raise ReferenceNotFound() from exc
