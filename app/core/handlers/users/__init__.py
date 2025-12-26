from aiogram import Router

from . import auth
from . import settings


def setup_user_management_routers() -> Router:
    router = Router()
    router.include_router(auth.router)
    router.include_router(settings.router)
    return router
