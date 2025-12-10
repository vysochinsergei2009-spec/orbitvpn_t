# Диагностика проблемы с YooKassa API

## Обнаруженная проблема

**Сетевая проблема**: Запросы к `api.yookassa.ru` таймаутятся на уровне TCP подключения.

### Доказательства:

1. **Из логов бота:**
   ```
   ConnectTimeoutError: Connection to api.yookassa.ru timed out. (connect timeout=None)
   ```

2. **Тест с curl:**
   - Подключение устанавливается (TLS handshake проходит)
   - Но запрос зависает и таймаутится через 20 секунд

3. **Тест с Python requests:**
   - `ConnectTimeoutError: Connection to api.yookassa.ru timed out. (connect timeout=10)`
   - Запрос не может установить TCP соединение

## Возможные причины:

1. **Файрвол/сеть блокирует исходящие соединения к YooKassa**
   - Проверить iptables/firewall правила
   - Проверить, может ли сервер достучаться до других HTTPS API

2. **Проблемы с DNS**
   - Проверить резолвинг `api.yookassa.ru`
   - Проверить, может ли сервер резолвить другие домены

3. **Проблемы на стороне YooKassa**
   - Возможно, YooKassa блокирует IP адрес сервера
   - Возможно, временные проблемы с их API

4. **Проблема с таймаутами в коде**
   - `Configuration.timeout = 15` устанавливает общий таймаут, но не connect timeout
   - Если TCP подключение зависает, запрос может висеть долго

## Что нужно проверить:

1. **Доступность YooKassa API:**
   ```bash
   # Проверить DNS
   nslookup api.yookassa.ru
   dig api.yookassa.ru
   
   # Проверить TCP подключение
   telnet api.yookassa.ru 443
   nc -zv api.yookassa.ru 443
   
   # Проверить HTTPS
   curl -v --connect-timeout 10 https://api.yookassa.ru/v3/payments
   ```

2. **Файрвол:**
   ```bash
   # Проверить iptables правила
   iptables -L -n -v
   
   # Проверить, есть ли блокировки исходящих соединений
   ```

3. **Сеть:**
   ```bash
   # Проверить маршрутизацию
   traceroute api.yookassa.ru
   
   # Проверить, может ли сервер достучаться до других API
   curl -v https://httpbin.org/get
   ```

4. **Логи YooKassa SDK:**
   - Проверить, есть ли более детальные логи от yookassa SDK
   - Возможно, нужно включить debug режим

## Решения:

### 1. Улучшить обработку таймаутов в коде

**Проблема:** `Configuration.timeout = 15` не устанавливает connect timeout явно.

**Решение:** Добавить явный connect timeout и улучшить обработку ошибок:

```python
# В yookassa.py
import urllib3
urllib3.util.timeout.Timeout(connect=10, read=15)

# Или использовать requests напрямую с таймаутами
```

### 2. Добавить retry логику

**Проблема:** При таймауте запрос просто падает, нет повторных попыток.

**Решение:** Добавить retry на уровне приложения:

```python
async def create_payment_with_retry(self, ...):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return await self.create_payment(...)
        except (ConnectTimeoutError, TimeoutError) as e:
            if attempt < max_retries - 1:
                LOG.warning(f"YooKassa timeout, retrying... (attempt {attempt + 1}/{max_retries})")
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
            else:
                raise
```

### 3. Проверить сетевую доступность

**Проблема:** Сервер может быть заблокирован или не иметь доступа к YooKassa.

**Решение:** 
- Проверить файрвол
- Проверить, может ли сервер достучаться до YooKassa
- Возможно, нужно добавить исключение в файрвол

### 4. Улучшить логирование

**Проблема:** Недостаточно информации о том, что именно происходит.

**Решение:** Добавить более детальное логирование:
- Логировать попытки подключения
- Логировать таймауты
- Логировать ошибки сети

## Следующие шаги:

1. ✅ Проверить доступность YooKassa API с сервера
2. ✅ Проверить файрвол/сеть
3. ⏳ Улучшить обработку таймаутов в коде
4. ⏳ Добавить retry логику
5. ⏳ Улучшить логирование


