# CryptoBot Payment Gateway Setup

## Описание

CryptoBot - это криптовалютный платёжный шлюз для Telegram ботов, поддерживающий множество криптовалют (USDT, BTC, ETH, TON и др.).

## Установка

### 1. Установка зависимостей

```bash
pip install aiocryptopay
```

или

```bash
pip install -r requirements.txt
```

### 2. Получение API токена

1. Откройте [@CryptoBot](https://t.me/CryptoBot) в Telegram
2. Перейдите в меню: **API** → **Create Application**
3. Создайте новое приложение и получите токен
4. Скопируйте токен (формат: `1234:AAbb...`)

### 3. Настройка .env файла

Добавьте следующие переменные в ваш `.env` файл:

```env
# CryptoBot Payment Gateway
CRYPTOBOT_TOKEN='your_token_here'
CRYPTOBOT_TESTNET='false'  # Установите 'true' для тестовой сети
```

**Важно:** Для продакшна используйте `CRYPTOBOT_TESTNET='false'`

### 4. Запуск миграции базы данных

Выполните SQL миграцию для добавления поля extra_data:

```bash
psql -U orbitcorp -d orbitvpn -f migrations/add_payment_metadata.sql
```

или подключитесь к PostgreSQL и выполните:

```sql
ALTER TABLE payments ADD COLUMN IF NOT EXISTS extra_data JSONB;
CREATE INDEX IF NOT EXISTS idx_payments_extra_data ON payments USING gin (extra_data);
```

## Использование

После настройки пользователи увидят новый вариант оплаты "CryptoBot" при пополнении баланса:

1. Пользователь выбирает **Баланс** → **Пополнить баланс**
2. Выбирает способ оплаты **CryptoBot**
3. Выбирает или вводит сумму
4. Нажимает кнопку **Оплатить**
5. Переходит на страницу CryptoBot для оплаты
6. После оплаты баланс автоматически пополняется

## Поддерживаемые криптовалюты

CryptoBot поддерживает следующие криптовалюты:
- USDT (Tether)
- BTC (Bitcoin)
- ETH (Ethereum)
- TON (The Open Network)
- USDC (USD Coin)
- и другие...

По умолчанию в боте используется USDT. Вы можете изменить валюту в файле `app/payments/gateway/cryptobot.py` (параметр `asset` в методе `create_invoice`).

## Testnet режим

Для разработки и тестирования вы можете использовать testnet режим:

1. Получите testnet токен от [@CryptoTestnetBot](https://t.me/CryptoTestnetBot)
2. Установите `CRYPTOBOT_TESTNET='true'` в `.env`
3. Используйте testnet токен вместо продакшн токена

## Безопасность

- **Никогда** не коммитьте токен в репозиторий
- Используйте переменные окружения для хранения чувствительных данных
- Для продакшна используйте mainnet токен (`CRYPTOBOT_TESTNET='false'`)
- Регулярно проверяйте логи на наличие подозрительной активности

## Troubleshooting

### Ошибка "CRYPTOBOT_TOKEN is not configured in .env"

Убедитесь, что:
1. Файл `.env` содержит строку `CRYPTOBOT_TOKEN='your_token'`
2. Токен не пустой
3. Вы перезапустили бота после изменения `.env`

### Платежи не подтверждаются автоматически

1. Проверьте логи бота на наличие ошибок
2. Убедитесь, что polling запущен (проверьте логи "Polling loop")
3. Проверьте, что платёж действительно прошёл в CryptoBot

### Инвойс не создаётся

1. Проверьте, что токен валиден
2. Проверьте интернет-соединение
3. Убедитесь, что используете правильную сеть (mainnet/testnet)

## Дополнительная информация

- [CryptoBot API Docs](https://help.crypt.bot/crypto-pay-api)
- [aiocryptopay Documentation](https://github.com/Foile/aiocryptopay)
- [CryptoBot Support](https://t.me/CryptoBotSupport)
