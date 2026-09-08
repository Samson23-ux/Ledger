import sentry_sdk
from fastapi import FastAPI
from contextlib import asynccontextmanager
from starlette.middleware.sessions import SessionMiddleware

from app.api.routers import router
from app.core.security import Security
from app.core.config import get_settings
from app.database.session import redis_client
from app.core.exception_handlers import ExceptionHandler
from app.api.services.circuit_breaker import CircuitBreaker

SECURITY = Security()
SETTINGS = get_settings()

sentry_sdk.init(
    dsn=SETTINGS.SENTRY_SDK_DSN,
    enable_logs=True,
    send_default_pii=True,
    traces_sample_rate=1.0,
    profiles_sample_rate=1.0,
    profile_lifecycle="trace",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await SECURITY.register_oauth()
    app.state.limiters = {}
    app.state.redis = redis_client

    breaker = CircuitBreaker()
    await breaker.initialize()

    yield

    await app.state.redis.aclose()


app = FastAPI(
    title=SETTINGS.API_TITLE,
    version=SETTINGS.API_VERSION,
    description=SETTINGS.API_DESCRIPTION,
    lifespan=lifespan,
)

app.include_router(router.router)

app.add_middleware(
    SessionMiddleware,
    max_age=900,
    same_site="lax",
    secret_key=SETTINGS.SESSION_SECRET_KEY,
    https_only=SETTINGS.ENVIRONMENT == "production",
)

exception_handler = ExceptionHandler(app)
exception_handler.add_handlers()


@app.get("/", status_code=200)
async def home():
    message: dict = {
        "status": "success",
        "message": "Welcome to Ledger",
    }
    return message
