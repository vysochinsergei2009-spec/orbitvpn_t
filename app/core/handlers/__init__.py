from aiogram import Router

from . import auth, configs, subscriptions, payments, settings, admin


def get_router() -> Router:
    main_router = Router()

    main_router.include_router(auth.router)
    main_router.include_router(configs.router)
    main_router.include_router(subscriptions.router)
    main_router.include_router(payments.router)
    main_router.include_router(settings.router)
    main_router.include_router(admin.router)

    return main_router


router = get_router()
