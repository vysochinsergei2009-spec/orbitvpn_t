  File "/root/orbitvpn/venv/lib/python3.12/site-packages/sqlalchemy/dialects/postgresql/asyncpg.py", line 797, in _handle_exception
    raise translated_error from error
sqlalchemy.exc.ProgrammingError: (sqlalchemy.dialects.postgresql.asyncpg.ProgrammingError) <class 'asyncpg.exceptions.InsufficientPrivilegeError'>: permission denied for table users
[SQL: SELECT users.tg_id AS users_tg_id, users.user_ip AS users_user_ip, users.balance AS users_balance, users.plan AS users_plan, users.subscription_end AS users_subscription_end, users.traffic_used AS users_traffic_used, users.max_traffic AS users_max_traffic, users.created_at AS users_created_at, users.username AS users_username, users.lang AS users_lang, users.configs AS users_configs, users.referrer_id AS users_referrer_id, users.first_buy AS users_first_buy 
FROM users 
WHERE users.tg_id = $1::BIGINT]
[parameters: (7559373710,)]
(Background on this error at: https://sqlalche.me/e/20/f405)