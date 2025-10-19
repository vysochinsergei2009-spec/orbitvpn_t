from aiomarzban import MarzbanAPI, UserDataLimitResetStrategy

from app.utils.logging import get_logger

from config import S001_BASE_URL, S001_MARZBAN_USERNAME, S001_MARZBAN_PASSWORD

marzban = MarzbanAPI(
    address=S001_BASE_URL,
    username=S001_MARZBAN_USERNAME,
    password=S001_MARZBAN_PASSWORD,
    default_proxies={"vless": {"flow": ""}}
)

LOG = get_logger(__name__)

async def marzban_add_user(username: str, days: int, data_limit: int = 50):
    try:
        new_user = await marzban.add_user(
            username=username,
            days=days,
            data_limit=data_limit,
            data_limit_reset_strategy=UserDataLimitResetStrategy.month,
        )
        if not new_user.links:
            raise ValueError("No VLESS link returned from Marzban")
        return new_user
    except Exception as e:
        LOG.error(f"Marzban add_user error: {e}")
        raise

async def marzban_remove_user(username: str):
    try:
        await marzban.remove_user(username)
    except Exception as e:
        LOG.error(f'Marzban remove_user error: {e}')
        raise

async def marzban_get_user(username: str):
    try:
        return await marzban.get_user(username)
    except Exception as e:
        LOG.error(f"Marzban get_user error: {e}")
        raise

async def marzban_renew_user(username: str, additional_days: int = 30):
    try:
        user = await marzban_get_user(username)
        import time
        now = time.time()
        new_expire = max(user.expire or 0, now) + additional_days * 86400
        await marzban.modify_user(username, expire=int(new_expire))
    except Exception as e:
        LOG.error(f"Marzban renew_user error: {e}")
        raise

async def marzban_modify_user(username: str, **kwargs):
    try:
        await marzban.modify_user(username, **kwargs)
    except Exception as e:
        LOG.error(f"Marzban modify_user error: {e}")
        raise