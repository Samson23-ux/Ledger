import secrets
import sentry_sdk
from uuid import uuid7, UUID
import sentry_sdk.logger as sentry_logger
from datetime import datetime, timezone, timedelta

from app.api.models.otp import Otp
from app.util import get_user_email
from app.api.models.user import User
from app.core.security import Security
from app.core.config import get_settings
from app.api.repo.otp import OtpRepository
from app.api.schemas.email import EmailInDB
from app.api.services.otp import OtpService
from app.api.services.otp import OtpService
from app.api.repo.user import UserRepository
from app.api.services.user import UserService
from app.api.repo.email import EmailRepository
from app.api.repo.redis import RedisRepository
from app.api.services.email import EmailService
from app.email_texts import verification_message
from app.api.repo.wallets import WalletRepository
from app.api.repo.uow import UnitOfWorkRepository
from app.api.services.wallets import WalletService
from app.api.services.thread_pool import ThreadPool
from app.worker.tasks.email import send_email
from app.api.schemas.user import (
    UserInDB,
    EmailUserResponse,
    GoogleUserResponse,
)
from app.api.schemas.auth import (
    EmailLogin,
    TokenData,
    EmailVerify,
    ResendOtp,
    UserSignUp,
    OtpInDB,
)
from app.core.exceptions import (
    UserExistsError,
    InvalidOtpError,
    ServerError,
    CredentialError,
    AuthenticationError,
)


class AuthService:
    def __init__(self, redis_repo: RedisRepository, pool: ThreadPool):
        self._uow = None
        self._pool = pool
        self._redis_repo = redis_repo

    SETTINGS = get_settings()

    async def _setup_uow(self, uow: UnitOfWorkRepository):
        self._uow = uow

    async def _uow_user_wallet(self, uow: UnitOfWorkRepository, with_otp: bool = False):
        await self._setup_uow(uow)

        user_repo = self._uow.repo(UserRepository)
        wallet_repo = self._uow.repo(WalletRepository)

        self._user_service = UserService(
            user_repo=user_repo, redis_repo=self._redis_repo
        )
        self._wallet_service = WalletService(
            pool=self._pool, wallet_repo=wallet_repo, redis_repo=self._redis_repo
        )

        if with_otp:
            otp_repo = self._uow.repo(OtpRepository)
            self._otp_service = OtpService(otp_repo=otp_repo)

    async def _uow_user_otp_email(self, uow: UnitOfWorkRepository):
        await self._setup_uow(uow)

        otp_repo = self._uow.repo(OtpRepository)
        user_repo = self._uow.repo(UserRepository)
        email_repo = self._uow.repo(EmailRepository)

        self._user_service = UserService(
            user_repo=user_repo, redis_repo=self._redis_repo
        )
        self._otp_service = OtpService(otp_repo=otp_repo)
        self._email_service = EmailService(email_repo=email_repo)

    async def _get_tokens(self, email: str, user_type: str, security: Security):
        token_data: TokenData = TokenData(email=email, user_type=user_type)
        access_token, refresh_token_payload = await security.prepare_tokens(token_data)

        refresh_token_id: str = refresh_token_payload.get("refresh_token_id")
        key: str = f"tokens:{refresh_token_id}"

        try:
            await self._redis_repo.create_hset(key, refresh_token_payload)
            return access_token, refresh_token_payload.get("refresh_token")
        except Exception as exc:
            sentry_sdk.capture_exception(exc)
            sentry_logger.error("Error occurred while saving refresh token to redis")
            raise ServerError() from exc

    async def _revoke_refresh_token(
        self, refresh_token: str, security: Security
    ) -> tuple:
        refresh_token: dict = await security.decode_token(
            refresh_token, self.SETTINGS.REFRESH_TOKEN_SECRET_KEY
        )

        if not refresh_token:
            sentry_logger.error("Inavlid refresh token received during refresh")
            raise AuthenticationError()

        refresh_token_id: str = refresh_token["jti"]
        key: str = f"tokens:{refresh_token_id}"

        refresh_token_db: dict = await self._redis_repo.get_hset(key)

        if not refresh_token_db:
            sentry_logger.error("Inavlid refresh token received during refresh")
            raise AuthenticationError()

        user_email: str = refresh_token_db["email"]
        user_type: str = refresh_token_db["user_type"]

        try:
            await self._redis_repo.delete_key(key)
            return user_email, user_type
        except Exception as exc:
            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occurred while deleting refresh token from redis"
            )
            raise ServerError() from exc

    async def _send_email(self, email_id: UUID, recipient_email: str, user_id: UUID):
        otp: str = str(secrets.randbelow(900000) + 100000)

        otp_payload: OtpInDB = OtpInDB(
            otp=otp,
            user_id=user_id,
            expires_at=datetime.now(timezone.utc)
            + timedelta(minutes=self.SETTINGS.OTP_EXPIRE_TIME),
        )
        await self._otp_service.create_otp(otp_payload, recipient_email)

        send_email.apply_async(
            priority=3,
            kwargs={
                "email_message": verification_message(otp),
                "email_id": str(email_id),
                "recipient_email": recipient_email,
            },
        )

    async def sign_up_with_email(
        self,
        sign_up_payload: UserSignUp,
        security: Security,
        uow: UnitOfWorkRepository,
    ):
        try:
            await self._uow_user_otp_email(uow)

            email_id: UUID = uuid7()

            user_email: str = sign_up_payload.email
            last_name: str = sign_up_payload.last_name
            first_name: str = sign_up_payload.first_name
            hashed_password: str = await security.hash_password(
                sign_up_payload.password
            )

            existing_user: User | None = await self._user_service._get_user_by_email(
                email=user_email
            )

            if existing_user:
                if not existing_user.is_verified:
                    existing_user.last_name = last_name
                    existing_user.first_name = first_name
                    existing_user.hashed_password = hashed_password

                    await self._user_service.update_user(existing_user)

                    email_db: EmailInDB = EmailInDB(
                        id=email_id, processed_email=existing_user.email
                    )
                    await self._email_service.create_email(email_db)

                    await self._send_email(
                        email_id, existing_user.email, existing_user.id
                    )
                else:
                    sentry_logger.error(
                        "User exists with email {email}", email=user_email
                    )
                    raise UserExistsError(user_email=user_email)
            else:
                user = UserInDB(
                    id=uuid7(),
                    email=user_email,
                    first_name=first_name,
                    last_name=last_name,
                    hashed_password=hashed_password,
                    type="email",
                )
                user: User = await self._user_service.create_user(user, user_email)

                email_db: EmailInDB = EmailInDB(id=email_id, processed_email=user_email)
                await self._email_service.create_email(email_db)

                await self._send_email(email_id, user_email, user.id)

            await self._uow.commit()

            sentry_logger.info(
                "Email and password sign up completed for user {email}",
                email=user_email,
            )
        except Exception as exc:
            if isinstance(exc, UserExistsError):
                raise UserExistsError(user_email=user_email)

            await self._uow.rollback()

            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while creating user",
            )
            raise ServerError() from exc

    async def sign_up_with_google(
        self, payload: dict, uow: UnitOfWorkRepository, security: Security
    ) -> tuple[str]:
        try:
            user_email = None
            await self._uow_user_wallet(uow)
            
            user_info: dict = payload.get("userinfo")
            
            google_id: str = user_info.get("sub")
            user_email: str = user_info.get("email")
            first_name: str = user_info.get("given_name")
            last_name: str = user_info.get("family_name")
            
            if not first_name or last_name and user_info.get("name"):
                parts = user_info["name"].split(" ", 1)
                first_name = parts[0]
                last_name = parts[1] if len(parts) > 1 else ""
            
            existing_user: User | None = await self._user_service._get_user_by_email(
                google_email=user_email,
                is_verified=True,
            )
            
            if existing_user:
                existing_user.is_active = True
                await self._user_service.update_user(existing_user)
            else:
                user = UserInDB(
                    id=uuid7(),
                    type="google",
                    is_active=True,
                    is_verified=True,
                    first_name=first_name,
                    last_name=last_name,
                    google_id=google_id,
                    google_email=user_email,
                )
                await self._user_service.create_user(user, user_email)
                await self._wallet_service._create_wallet(user.id)
            
            access_token, refresh_token = await self._get_tokens(
                user_email, "google", security
            )
            
            await self._uow.commit()
            
            sentry_logger.info(
                "Google sign in completed for user {email}",
                email=user_email,
            )
            
            return access_token, refresh_token
        except Exception as exc:
            await self._uow.rollback()

            email = user_email if user_email else ""

            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while sigining in with google account",
                extra={"email": email}
            )
            raise ServerError() from exc

    async def verify_account(
        self,
        uow: UnitOfWorkRepository,
        email_verify: EmailVerify,
    ):
        await self._uow_user_wallet(uow, with_otp=True)

        user_email: str = email_verify.email
        existing_user: User | None = await self._user_service._get_user_by_email(
            email=user_email
        )

        if not existing_user:
            sentry_logger.error("User not found with email {email}", email=user_email)
            raise InvalidOtpError()

        otp: Otp = await self._otp_service.get_otp(
            otp=email_verify.otp_code,
            user_id=existing_user.id,
            status="valid",
            expires_at=True,
        )

        if not otp:
            sentry_logger.error(
                "Invalid otp received from user {email}", email=user_email
            )
            raise InvalidOtpError()

        try:
            otp.status = "used"
            existing_user.is_verified = True

            await self._otp_service.update_otp(otp, user_email)
            await self._user_service.update_user(existing_user)
            await self._wallet_service._create_wallet(existing_user.id)

            await self._uow.commit()

            sentry_logger.info(
                "User {email} account verification completed",
                email=user_email,
            )
        except Exception as exc:
            await self._uow.rollback()

            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while trying to verify user {email} account",
                email=user_email,
            )
            raise ServerError() from exc

    async def resend_otp(
        self,
        otp_resend: ResendOtp,
        uow: UnitOfWorkRepository,
    ):
        await self._uow_user_otp_email(uow)
        user_email: str = otp_resend.email

        existing_user: User | None = await self._user_service._get_user_by_email(
            email=user_email, is_verified=False
        )

        if not existing_user:
            sentry_logger.error("User with email {email} not found", email=user_email)
            raise CredentialError()

        try:
            # invalidate all existing codes
            await self._otp_service.bulk_update_otp(
                {"status": "used"},
                email=user_email,
                user_id=existing_user.id,
                status="valid",
            )

            email_id: UUID = uuid7()
            email_db: EmailInDB = EmailInDB(
                id=email_id, processed_email=existing_user.email
            )
            await self._email_service.create_email(email_db)

            await self._send_email(email_id, user_email, existing_user.id)

            await self._uow.commit()

            sentry_logger.info(
                "OTP code resent to user {email}",
                email=user_email,
            )
        except Exception as exc:
            await self._uow.rollback()

            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while resending otp to user {email}",
                email=user_email,
            )
            raise ServerError() from exc

    async def login(
        self, email_login: EmailLogin, user_service: UserService, security: Security
    ):
        user_email: str = email_login.email
        existing_user: User | None = await user_service._get_user_by_email(
            email=user_email, is_verified=True
        )

        if not existing_user:
            sentry_logger.error(
                "Invalid credentials received from user {email}", email=user_email
            )
            raise CredentialError()

        if not await security.verify_password(
            email_login.password, existing_user.hashed_password
        ):
            sentry_logger.error(
                "Invalid credentials received from user {email}", email=user_email
            )
            raise CredentialError()

        existing_user.is_active = True
        await user_service.update_user(existing_user, commit=True)

        access_token, refresh_token = await self._get_tokens(
            user_email, "email", security
        )

        sentry_logger.info(
            "Login completed for user {email}",
            email=user_email,
        )

        return access_token, refresh_token

    async def create_auth_tokens(self, refresh_token: str, security: Security):
        user_email, user_type = await self._revoke_refresh_token(
            refresh_token, security
        )
        access_token, refresh_token = await self._get_tokens(
            user_email, user_type, security
        )

        sentry_logger.info(
            "Access and refresh tokens created for user {email}",
            email=user_email,
        )

        return access_token, refresh_token

    async def get_current_user(
        self, curr_user: User
    ) -> EmailUserResponse | GoogleUserResponse:
        if curr_user.type == "email":
            user_email: str = curr_user.email
            user = EmailUserResponse.model_validate(curr_user)
        else:
            user_email: str = curr_user.google_email
            user = GoogleUserResponse.model_validate(curr_user)

        sentry_logger.info(
            "User {email} account retrieved",
            email=user_email,
        )
        return user

    async def logout(
        self,
        curr_user: User,
        user_service: UserService,
        refresh_token: str,
        security: Security,
    ):
        user_email: str = get_user_email(curr_user)
        _ = await self._revoke_refresh_token(refresh_token, security)

        curr_user.is_active = False
        await user_service.update_user(curr_user, commit=True)

        sentry_logger.info(
            "User {email} account logout completed",
            email=user_email,
        )

    async def delete_account(
        self,
        curr_user: User,
        user_service: UserService,
        refresh_token: str,
        security: Security,
    ):
        user_email: str = get_user_email(curr_user)
        await user_service.delete_user(curr_user)
        _ = await self._revoke_refresh_token(refresh_token, security)

        sentry_logger.info(
            "User {email} account deleted",
            email=user_email,
        )
