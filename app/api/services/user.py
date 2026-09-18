import sentry_sdk
import sentry_sdk.logger as sentry_logger

from app.api.models.user import User
from app.core.config import get_settings
from app.api.schemas.user import UserInDB
from app.api.repo.user import UserRepository
from app.api.repo.redis import RedisRepository
from app.core.exceptions import ServerError, UserNotFoundError
from app.serializers import _serialize_user, _deserialize_cached_user

SETTINGS = get_settings()


class UserService:
    def __init__(self, user_repo: UserRepository, redis_repo: RedisRepository):
        self._user_repo = user_repo
        self._redis_repo = redis_repo

    @staticmethod
    def _user_cache_key(email: str, user_type: str) -> str:
        return f"user:{email}:{user_type}"

    async def get_user_by_email(self, **filters) -> User:
        if "email" in filters:
            user_email: str = filters["email"]
        elif "google_email" in filters:
            user_email: str = filters["google_email"]

        try:
            user: User | None = await self._user_repo.get_record(**filters)

            if not user:
                sentry_logger.error(
                    "User not found with email {email}", email=user_email
                )
                raise UserNotFoundError(user_email=user_email)

            return user
        except Exception as exc:
            if isinstance(exc, UserNotFoundError):
                raise UserNotFoundError(user_email=user_email) from exc

            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while retrieving user with email {email}",
                email=user_email,
            )
            raise ServerError() from exc

    async def _get_user_by_email(self, **filters) -> User | None:
        return await self._user_repo.get_record(**filters)

    async def create_user(
        self, user: UserInDB, email: str, commit: bool = False
    ) -> User:
        try:
            user: User = self._user_repo.add(entity=user)

            if commit:
                await self._user_repo.commit()
                await self._user_repo.refresh(user)
            else:
                await self._user_repo.flush()
                await self._user_repo.refresh(user)

            return user
        except Exception as exc:
            if commit:
                await self._user_repo.rollback()

            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while creating user with email {email}", email=email
            )
            raise ServerError() from exc

    async def get_cached_user(self, **filters) -> User | None:
        user_email: str = filters.get("email") or filters.get("google_email")
        cache_key: str = self._user_cache_key(user_email, filters.get("user_type"))

        cached: dict = await self._redis_repo.get_hset(cache_key)

        if cached:
            cached_user = _deserialize_cached_user(cached)

            if not cached_user.is_verified:
                sentry_logger.error(
                    "User not found with email {email}", email=user_email
                )
                raise UserNotFoundError(user_email=user_email)

            return cached_user
        return

    async def cache_user(self, user: User):
        value: dict = _serialize_user(user)

        if user.email:
            await self._redis_repo.create_hset(
                self._user_cache_key(user.email, "email"), value
            )
        if user.google_email:
            await self._redis_repo.create_hset(
                self._user_cache_key(user.google_email, "google"), value
            )

    async def invalidate_user_cache(self, user: User):
        if user.email:
            await self._redis_repo.delete_key(self._user_cache_key(user.email, "email"))
        if user.google_email:
            await self._redis_repo.delete_key(
                self._user_cache_key(user.google_email, "google")
            )

    async def update_user(self, user: User, commit: bool = False) -> User:
        try:
            user_email: str = user.email
            user: User = self._user_repo.add(model=user)

            if commit:
                await self._user_repo.commit()
                await self._user_repo.refresh(user)
            else:
                await self._user_repo.flush()
                await self._user_repo.refresh(user)

            await self.cache_user(user)

            return user
        except Exception as exc:
            if commit:
                await self._user_repo.rollback()

            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while updating user with email {email}", email=user_email
            )
            raise ServerError() from exc

    async def delete_user(self, user: User):
        try:
            user_email: str = user.email
            await self._user_repo.delete(user)
            await self._user_repo.commit()
            await self.invalidate_user_cache(user)
        except Exception as exc:
            await self._user_repo.rollback()
            sentry_sdk.capture_exception(exc)
            sentry_logger.error(
                "Error occured while deleting user with email {email}", email=user_email
            )
            raise ServerError() from exc
