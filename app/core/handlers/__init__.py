from aiogram import Router

from .users import setup_user_management_routers
from .servers import setup_vpn_management_routers
from .billing import setup_billing_routers
# from .admin import setup_admin_routers # Not present in app/core/handlers

__all__ = [
    "setup_handlers",
]


def setup_handlers() -> Router:
    router = Router()
    router.include_router(setup_user_management_routers())
    router.include_router(setup_vpn_management_routers())
    router.include_router(setup_billing_routers())
    # router.include_router(setup_admin_routers()) # Not present in app/core/handlers

    return router