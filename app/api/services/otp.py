import sentry_sdk
import sentry_sdk.logger as sentry_logger

from app.api.models.otp import Otp
from app.api.schemas.auth import OtpInDB
from app.api.repo.otp import OtpRepository
from app.core.exceptions import ServerError


class OtpService:
    def __init__(self, otp_repo: OtpRepository):
        self._otp_repo = otp_repo

    async def get_otp(self, **filters) -> Otp | None:
        return await self._otp_repo.get_record(**filters)

    def create_otp(self, otp: OtpInDB, email: str):
        try:
            self._otp_repo.sync_add(entity=otp)
            self._otp_repo.sync_commit()
        except Exception as exc:
            self._otp_repo.sync_rollback()
            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while creating otp for user with email {email}",
                email=email,
            )
            raise ServerError() from exc

    async def update_otp(self, otp: Otp, email: str) -> Otp:
        try:
            otp: Otp = self._otp_repo.add(model=otp)

            await self._otp_repo.commit()
            return otp
        except Exception as exc:
            await self._otp_repo.rollback()
            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while updating otp for user with email {email}",
                email=email,
            )
            raise ServerError() from exc

    async def bulk_update_otp(self, update_values: dict, **filters):
        try:
            email: str = filters["email"]
            await self._otp_repo.update_records(update_values, **filters)
            await self._otp_repo.commit()
        except Exception as exc:
            await self._otp_repo.rollback()
            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while updating otp status for user with email {email}",
                email=email,
            )
            raise ServerError() from exc
