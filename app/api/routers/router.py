from fastapi import APIRouter

from app.api.routers import auth
from app.deps import auth_limiter
from app.core.config import get_settings

SETTINGS = get_settings()

router = APIRouter(prefix=SETTINGS.API_PREFIX)
router.include_router(auth.router, tags=["Auth"], dependencies=[auth_limiter])
