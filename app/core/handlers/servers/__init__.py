from aiogram import Router

from . import configs
from . import subscriptions


def setup_vpn_management_routers() -> Router:
    router = Router()
    router.include_router(configs.router)
    router.include_router(subscriptions.router)
    return router
