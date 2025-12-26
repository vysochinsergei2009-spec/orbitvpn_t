from aiogram import Router

from . import payments


def setup_billing_routers() -> Router:
    router = Router()
    router.include_router(payments.router)
    return router
