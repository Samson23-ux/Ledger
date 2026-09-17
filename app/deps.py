from typing import Annotated
from redis.asyncio import Redis
from fastapi import Depends, Request
import sentry_sdk.logger as sentry_logger
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.api.models.user import User
from app.core.security import Security
from app.core.config import get_settings
from app.limiter import _limiter_handler
from app.core.config import get_settings
from app.api.repo.otp import OtpRepository
from app.api.services.otp import OtpService
from app.database.session import get_session
from app.api.repo.user import UserRepository
from app.api.services.auth import AuthService
from app.api.services.user import UserService
from app.api.repo.email import EmailRepository
from app.api.repo.redis import RedisRepository
from app.api.services.email import EmailService
from app.api.repo.outbox import OutBoxRepository
from app.api.services.outbox import OutBoxService
from app.api.repo.uow import UnitOfWorkRepository

from app.api.repo.wallets import WalletRepository
from app.api.repo.refunds import RefundRepository
from app.api.services.refunds import RefundService
from app.api.services.wallets import WalletService
from app.api.services.thread_pool import ThreadPool
from app.core.exceptions import AuthenticationError
from app.api.repo.refund_state import RefundStateRepository
from app.api.repo.transactions import TransactionRepository
from app.api.services.circuit_breaker import CircuitBreaker
from app.api.services.transactions import TransactionService
from app.api.services.refund_state import RefundStateService
from app.api.repo.webhook_events import WebhookEventRepository
from app.api.repo.wallet_credits import WalletCreditRepository
from app.api.services.wallet_credits import WalletCreditService
from app.api.repo.authorization_codes import AuthCodeRepository
from app.api.services.webhook_events import WebhookEventService
from app.api.services.authorization_codes import AuthCodeService
from app.api.services.payment_gateway import Transaction, Refund
from app.api.repo.transaction_state import TransactionStateRepository
from app.api.services.transaction_state import TransactionStateService

SETTINGS = get_settings()

# Auth bearer
bearer = HTTPBearer(auto_error=False)

# ------------------- DB dependency ------------------------------ #

DBSession = Annotated[AsyncSession, Depends(get_session)]


# ------------------- Redis dependency ------------------------------ #
async def get_redis_client(request: Request) -> Redis:
    redis_client: Redis = request.app.state.redis
    return redis_client


RedisDep = Annotated[Redis, Depends(get_redis_client)]


# ------------------- Security dependency ------------------------------ #
async def get_security() -> Security:
    return Security()


SecurityDep = Annotated[Security, Depends(get_security)]

#  ------------------- Repo dependency ----------------------------- #


async def get_otp_repo(session: DBSession) -> OtpRepository:
    return OtpRepository(async_session=session)


async def get_user_repo(session: DBSession) -> UserRepository:
    return UserRepository(async_session=session)


async def get_redis_repo(redis: RedisDep) -> RedisRepository:
    return RedisRepository(async_redis=redis)


async def get_email_repo(session: DBSession) -> EmailRepository:
    return EmailRepository(async_session=session)


async def get_unit_of_work(session: DBSession) -> UnitOfWorkRepository:
    return UnitOfWorkRepository(async_session=session)


async def get_wallet_repo(session: DBSession) -> WalletRepository:
    return WalletRepository(async_session=session)


async def get_auth_code_repo(session: DBSession) -> AuthCodeRepository:
    return AuthCodeRepository(async_session=session)


async def get_out_box_repo(session: DBSession) -> OutBoxRepository:
    return OutBoxRepository(async_session=session)


async def get_credit_repo(session: DBSession) -> WalletCreditRepository:
    return WalletCreditRepository(async_session=session)


async def get_transaction_repo(session: DBSession) -> TransactionRepository:
    return TransactionRepository(async_session=session)


async def get_transaction_state_repo(session: DBSession) -> TransactionStateRepository:
    return TransactionStateRepository(async_session=session)


async def get_webhook_repo(session: DBSession) -> WebhookEventRepository:
    return WebhookEventRepository(async_session=session)


async def get_refund_repo(session: DBSession) -> RefundRepository:
    return RefundRepository(async_session=session)


async def get_refund_state_repo(session: DBSession) -> RefundStateRepository:
    return RefundStateRepository(async_session=session)


OtpRepo = Annotated[OtpRepository, Depends(get_otp_repo)]
UserRepo = Annotated[UserRepository, Depends(get_user_repo)]
RedisRepo = Annotated[RedisRepository, Depends(get_redis_repo)]
EmailRepo = Annotated[EmailRepository, Depends(get_email_repo)]
WalletRepo = Annotated[WalletRepository, Depends(get_wallet_repo)]
OutBoxRepo = Annotated[OutBoxRepository, Depends(get_out_box_repo)]
RefundRepo = Annotated[RefundRepository, Depends(get_refund_repo)]
AuthCodeRepo = Annotated[AuthCodeRepository, Depends(get_auth_code_repo)]
UnitOfWorkRepo = Annotated[UnitOfWorkRepository, Depends(get_unit_of_work)]
WalletCreditRepo = Annotated[WalletCreditRepository, Depends(get_credit_repo)]
WebhookEventRepo = Annotated[WebhookEventRepository, Depends(get_webhook_repo)]
TransactionRepo = Annotated[TransactionRepository, Depends(get_transaction_repo)]
RefundStateRepo = Annotated[RefundStateRepository, Depends(get_refund_state_repo)]
TransactionStateRepo = Annotated[
    TransactionStateRepository, Depends(get_transaction_state_repo)
]

#  -------------------- Service dependency ---------------------------- #


async def get_user_service(user_repo: UserRepo, redis_repo: RedisRepo) -> UserService:
    return UserService(user_repo=user_repo, redis_repo=redis_repo)


async def get_email_service(email_repo: EmailRepo) -> EmailService:
    return EmailService(email_repo=email_repo)


async def get_thread_pool() -> ThreadPool:
    return ThreadPool()


ThreadPoolDep = Annotated[ThreadPool, Depends(get_thread_pool)]


async def get_auth_service(redis_repo: RedisRepo, pool: ThreadPoolDep) -> AuthService:
    return AuthService(redis_repo=redis_repo, pool=pool)


async def get_otp_service(otp_repo: OtpRepo) -> OtpService:
    return OtpService(otp_repo=otp_repo)


async def get_circuit_breaker(redis_repo: RedisRepo) -> CircuitBreaker:
    return CircuitBreaker(redis=redis_repo)


async def get_wallet_service(
    pool: ThreadPoolDep, redis_repo: RedisRepo, wallet_repo: WalletRepo
) -> WalletService:
    return WalletService(pool=pool, wallet_repo=wallet_repo, redis_repo=redis_repo)


async def get_refund() -> Refund:
    return Refund(api_key=SETTINGS.PAYSTACK_API_KEY)


async def get_transaction() -> Transaction:
    return Transaction(api_key=SETTINGS.PAYSTACK_API_KEY)


async def get_auth_code_service(code_repo: AuthCodeRepo) -> AuthCodeService:
    return AuthCodeService(code_repo=code_repo)


async def get_out_box_service(out_box_repo: OutBoxRepo) -> OutBoxService:
    return OutBoxService(out_box_repo=out_box_repo)


async def get_credit_service(credit_repo: WalletCreditRepo) -> WalletCreditService:
    return WalletCreditService(credit_repo=credit_repo)


async def get_transaction_service(
    pool: ThreadPoolDep, transaction_repo: TransactionRepo,
) -> TransactionService:
    return TransactionService(pool=pool, transaction_repo=transaction_repo)


async def get_transaction_state_service(
    state_repo: TransactionStateRepo,
) -> TransactionStateService:
    return TransactionStateService(state_repo=state_repo)


async def get_webhook_service(webhook_repo: WebhookEventRepo) -> WebhookEventService:
    return WebhookEventService(webhook_repo=webhook_repo)


async def get_refund_service(
    pool: ThreadPoolDep, redis_repo: RedisRepo, refund_repo: RefundRepo
) -> RefundService:
    return RefundService(pool=pool, redis_repo=redis_repo, refund_repo=refund_repo)


async def get_refund_state_service(
    state_repo: RefundStateRepo,
) -> RefundStateService:
    return RefundStateService(state_repo=state_repo)


RefundDep = Annotated[Refund, Depends(get_refund)]
OtpServiceDep = Annotated[OtpService, Depends(get_otp_service)]
TransactionDep = Annotated[Transaction, Depends(get_transaction)]
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
UserServiceDep = Annotated[UserService, Depends(get_user_service)]
EmailServiceDep = Annotated[EmailService, Depends(get_email_service)]
RefundServiceDep = Annotated[RefundService, Depends(get_refund_service)]
WalletServiceDep = Annotated[WalletService, Depends(get_wallet_service)]
OutBoxServiceDep = Annotated[OutBoxService, Depends(get_out_box_service)]
CircuitBreakerDep = Annotated[CircuitBreaker, Depends(get_circuit_breaker)]
AuthCodeServiceDep = Annotated[AuthCodeService, Depends(get_auth_code_service)]
WalletCreditServiceDep = Annotated[WalletCreditService, Depends(get_credit_service)]
WebhookEventServiceDep = Annotated[WebhookEventService, Depends(get_webhook_service)]
TransactionServiceDep = Annotated[TransactionService, Depends(get_transaction_service)]
RefundStateServiceDep = Annotated[RefundStateService, Depends(get_refund_state_service)]
TransactionStateServiceDep = Annotated[
    TransactionStateService, Depends(get_transaction_state_service)
]

# ------------------------ Auth dependency ---------------------------- #


async def _decode_credentials(
    security: SecurityDep,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer)],
) -> tuple[str, str]:
    """Returns (user_email_or_google_email, user_type) from a validated JWT."""
    if not credentials:
        sentry_logger.error("User not authenticated")
        raise AuthenticationError()

    token: str | None = credentials.credentials
    key: str = get_settings().ACCESS_TOKEN_SECRET_KEY

    payload: dict = await security.decode_token(token, key)

    if not payload:
        sentry_logger.error("User not authenticated")
        raise AuthenticationError()

    return payload.get("sub"), payload.get("usertype")


async def get_current_user(
    user_service: UserServiceDep,
    identity: Annotated[tuple[str, str], Depends(_decode_credentials)],
) -> User:
    filters: dict = {}
    user_email, user_type = identity

    if user_type == "email":
        filters["email"] = user_email
    else:
        filters["google_email"] = user_email

    user: User = await user_service.get_user_by_email(**filters)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_active_user(curr_user: CurrentUser):
    if curr_user.is_active is False:
        raise AuthenticationError()
    return curr_user


CurrentActiveUser = Annotated[User, Depends(get_current_active_user)]


async def get_cached_current_user(
    user_service: UserServiceDep,
    identity: Annotated[tuple[str, str], Depends(_decode_credentials)],
):
    filters: dict = {}
    user_email, user_type = identity

    if user_type == "email":
        filters["email"] = user_email
    else:
        filters["google_email"] = user_email

    user: User = await user_service.get_cached_user(**filters)

    if not user:
        filters["is_verified"] = True
        user: User = await user_service.get_user_by_email(**filters)

        await user_service.cache_user(user)
    return user


CachedCurrentUser = Annotated[User, Depends(get_cached_current_user)]


async def get_current_active_cached_user(cached_user: CachedCurrentUser):
    if cached_user.is_active is False:
        raise AuthenticationError()
    return cached_user


CurrentActiveCachedUser = Annotated[User, Depends(get_current_active_cached_user)]


# ------------------------ Limiter -------------------------------- #
auth_limiter = Depends(
    _limiter_handler(
        key=SETTINGS.AUTH_LIMIT_KEY, limit=10, unit="minutes", multiplier=15
    )
)

get_default = Depends(
    _limiter_handler(
        key=SETTINGS.AUTH_LIMIT_KEY, limit=10, unit="minutes", multiplier=1
    )
)

fund_wallet_limiter = Depends(
    _limiter_handler(
        key=SETTINGS.AUTH_LIMIT_KEY, limit=10, unit="minutes", multiplier=15
    )
)
