from aiogram import Router

from app.admin import router as admin_router
from . import auth, configs, subscriptions, payments, settings, admin


def get_router() -> Router:
    main_router = Router()

    main_router.include_router(auth.router)
    main_router.include_router(configs.router)
    main_router.include_router(subscriptions.router)
    main_router.include_router(payments.router)
    main_router.include_router(settings.router)
    main_router.include_router(admin.router)  # Promocode admin commands
    main_router.include_router(admin_router)

    return main_router


router = get_router()
