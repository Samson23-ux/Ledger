from fastapi import APIRouter


from app.core.config import get_settings
from app.api.routers import auth, wallets, transactions, webhook_events

SETTINGS = get_settings()

router = APIRouter(prefix=SETTINGS.API_PREFIX)
router.include_router(auth.router, tags=["Auth"])
router.include_router(wallets.router, tags=["Wallets"])
router.include_router(webhook_events.router, tags=["Webhooks"])
router.include_router(transactions.router, tags=["Transactions"])
