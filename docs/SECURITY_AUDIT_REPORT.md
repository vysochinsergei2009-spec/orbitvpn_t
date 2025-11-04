# Краткий Аудит Безопасности OrbitVPN

**Дата:** 2025-10-25
**Версия:** 0.5.4
**Общая оценка:** 7/10 (Хорошо, требуются улучшения)

---

## ✅ Что Работает Хорошо

### 1. Защита от Race Conditions
**Местоположение:** `app/repo/user.py:83-113`, `app/core/handlers/payments.py:298-364`, `app/payments/gateway/ton.py:84-156`

Отлично реализовано использование `SELECT FOR UPDATE` для критических операций:
- Изменение баланса
- Подтверждение платежей
- Создание конфигураций

```python
# app/repo/user.py:83-113
user = await session.get(User, user_id, with_for_update=True)  # ✅ Блокировка строки
user.balance += amount
await session.commit()
```

### 2. Авторизация при Удалении Конфигов
**Местоположение:** `app/repo/user.py:241-263`

Проверка владельца перед удалением:
```python
cfg = await self.session.get(Config, cfg_id)
if not cfg or cfg.tg_id != tg_id:  # ✅ Проверка владельца
    return
```

### 3. Redis Кэширование
**Местоположение:** `app/repo/user.py`

Оптимальное кэширование с TTL 300s для балансов, конфигов, подписок.

### 4. Rate Limiting
**Местоположение:** `app/utils/rate_limit.py`

Защита от спама с кастомными лимитами для разных операций.

### 5. Валидация Сумм Платежей
**Местоположение:** `app/core/handlers/payments.py:86-94, 103-114`

```python
if amount < 200 or amount > 100000:  # ✅ Лимиты
    raise ValueError("Invalid amount")
```

---

## 🔴 Критические Проблемы (Исправить Немедленно)

### КРИТ-1: Незащищенные Credentials Marzban
**Severity:** Critical
**Местоположение:** `app/repo/models.py`, `config.py`

**Проблема:** Пароли Marzban хранятся в БД в открытом виде.

**Исправление:**
```python
# Использовать Fernet для шифрования
from cryptography.fernet import Fernet

class MarzbanInstance(Base):
    password_encrypted = Column(String(500))

    def set_password(self, password: str, key: bytes):
        cipher = Fernet(key)
        self.password_encrypted = cipher.encrypt(password.encode()).decode()
```

**ENV Variable:**
```bash
ENCRYPTION_KEY=<generate with Fernet.generate_key()>
```

---

### КРИТ-2: Отсутствие Проверки TON Transaction Hash
**Severity:** Critical
**Местоположение:** `app/payments/gateway/ton.py`

**Проблема:** Один tx_hash может использоваться для подтверждения нескольких платежей.

**Исправление:**
```python
# app/repo/payments.py
async def is_tx_hash_used(self, tx_hash: str) -> bool:
    result = await self.session.execute(
        select(Payment).where(
            Payment.tx_hash == tx_hash,
            Payment.status == 'confirmed'
        )
    )
    return result.scalar_one_or_none() is not None

# В ton.py перед подтверждением
if await self.payment_repo.is_tx_hash_used(tx.tx_hash):
    LOG.warning(f"TX hash {tx.tx_hash} already used")
    return False
```

---

## 🟠 Высокий Приоритет (Исправить в Течение Недели)

### ВЫС-1: Trial Abuse
**Местоположение:** `app/core/handlers/auth.py`

**Проблема:** Пользователь может создавать множество аккаунтов для бесплатных trial.

**Исправление:**
```python
# Добавить таблицу для tracking
class TrialTracking(Base):
    telegram_id = Column(BigInteger)
    device_fingerprint = Column(String(255))  # IP hash
    granted_at = Column(DateTime)

# Проверять fingerprint перед выдачей trial
async def check_trial_eligibility(tg_id: int, ip_hash: str) -> bool:
    recent = await session.execute(
        select(TrialTracking).where(
            or_(
                TrialTracking.telegram_id == tg_id,
                TrialTracking.device_fingerprint == ip_hash
            ),
            TrialTracking.granted_at > datetime.utcnow() - timedelta(days=30)
        )
    )
    return recent.scalar_one_or_none() is None
```

---

### ВЫС-2: Лимит Конфигураций
**Местоположение:** `app/core/handlers/configs.py`

**Проблема:** Нет жесткого лимита на количество конфигов.

**Исправление:**
```python
MAX_CONFIGS_PER_USER = 5  # в config.py

async def add_config_handler(callback: CallbackQuery, t):
    configs = await user_repo.get_configs(tg_id)
    if len(configs) >= MAX_CONFIGS_PER_USER:
        await callback.answer(t('max_configs_reached'), show_alert=True)
        return
```

---

### ВЫС-3: Логирование Чувствительных Данных
**Местоположение:** `app/repo/user.py:104`, `app/core/handlers/payments.py`

**Проблема:** Балансы и суммы логируются в открытом виде.

**Исправление:**
```python
def sanitize_amount(amount: float) -> str:
    if amount < 100: return "<100"
    elif amount < 1000: return "100-1000"
    return ">1000"

LOG.info(f"Balance updated: {sanitize_amount(old_balance)} → {sanitize_amount(new_balance)}")
```

---

### ВЫС-4: Идемпотентность Платежей
**Местоположение:** `app/repo/payments.py`

**Проблема:** Повторные вызовы confirm_payment могут привести к проблемам.

**Исправление:**
```python
async def confirm_payment(self, payment_id: int):
    payment = await session.get(Payment, payment_id, with_for_update=True)

    if payment.status == 'confirmed':
        LOG.info(f"Payment {payment_id} already confirmed (idempotent)")
        return PaymentResult(success=True, idempotent=True)

    # Продолжить подтверждение
```

---

## 🟡 Средний Приоритет (Исправить в Течение Месяца)

### СР-1: Retry Logic для Marzban API
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=60))
async def call_marzban_api(self, endpoint: str):
    # ... запрос
```

### СР-2: Timeout для HTTP Запросов
```python
timeout = aiohttp.ClientTimeout(total=30, connect=5)
async with aiohttp.ClientSession(timeout=timeout) as session:
    # ...
```

### СР-3: N+1 Query в get_configs
```python
from sqlalchemy.orm import selectinload

result = await session.execute(
    select(Config)
    .options(selectinload(Config.marzban_instance))  # ✅ Eager loading
    .where(Config.user_id == user_id)
)
```

### СР-4: Health Check Endpoint
```python
# app/health.py
async def health_check(request):
    checks = {
        'database': await check_db(),
        'redis': await check_redis(),
        'marzban': await check_marzban()
    }
    status = 200 if all(checks.values()) else 503
    return web.json_response({'status': 'healthy' if status == 200 else 'unhealthy', 'checks': checks}, status=status)
```

---

## 🟢 Низкий Приоритет

1. **Docstrings**: Добавить документацию ко всем публичным методам
2. **Graceful Shutdown**: Корректное закрытие соединений при остановке
3. **Prometheus Metrics**: Мониторинг платежей, балансов, конфигов
4. **Dead Letter Queue**: Повторная обработка failed payments

---

## Приоритизация Исправлений

### Неделя 1 (Критические)
1. ✅ Шифрование Marzban credentials
2. ✅ Проверка уникальности TON tx_hash

### Неделя 2 (Высокий приоритет)
3. ✅ Trial abuse protection
4. ✅ Лимит конфигураций
5. ✅ Sanitization логов
6. ✅ Идемпотентность платежей

### Месяц 1 (Средний приоритет)
7. Retry logic + timeouts
8. N+1 query fixes
9. Health check endpoint

---

## Итоговая Оценка

| Категория | Оценка | Комментарий |
|-----------|--------|-------------|
| Безопасность платежей | 8/10 | ✅ SELECT FOR UPDATE, ⚠️ нужна защита от replay |
| Авторизация | 7/10 | ✅ Проверка владельца, ⚠️ trial abuse |
| Защита данных | 6/10 | ⚠️ Credentials в открытом виде, логи |
| Производительность | 8/10 | ✅ Redis cache, ⚠️ N+1 queries |
| Код-качество | 7/10 | ✅ Async, типизация, ⚠️ обработка ошибок |

**Общий результат:** 7.2/10 → **9/10** после исправлений критических и высокоприоритетных находок.

---

## Быстрый Чеклист для Внедрения

```bash
# 1. Добавить шифрование credentials
pip install cryptography
# Добавить ENCRYPTION_KEY в .env

# 2. Добавить проверку tx_hash в payments.py
# См. КРИТ-2 выше

# 3. Добавить trial tracking
# Создать миграцию для таблицы TrialTracking

# 4. Добавить лимиты конфигов
# Обновить config.py и handlers/configs.py

# 5. Исправить логирование
# Добавить sanitize функции в utils/logging.py
```

---

**Следующий аудит:** Через 3 месяца после внедрения исправлений.
