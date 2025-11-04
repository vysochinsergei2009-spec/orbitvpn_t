# OrbitVPN Service Manager - System Overview

## Что было создано

Полноценная система управления OrbitVPN с двумя интерфейсами (CLI и Web) для контроля бота и Marzban инфраструктуры.

## Структура проекта

```
/root/orbitvpn/
├── manager/                          # Основная директория менеджера
│   ├── core/                         # Ядро системы
│   │   ├── supervisor.py             # Главный супервизор сервисов
│   │   ├── service.py                # Базовая абстракция сервиса
│   │   ├── health.py                 # Система health checks
│   │   ├── metrics.py                # Сбор метрик
│   │   └── models.py                 # Модели данных
│   ├── services/                     # Реализации сервисов
│   │   ├── telegram_bot.py           # Управление Telegram ботом
│   │   ├── marzban.py                # Мониторинг Marzban
│   │   ├── redis.py                  # Мониторинг Redis
│   │   └── postgres.py               # Мониторинг PostgreSQL
│   ├── monitoring/                   # Мониторинг и алерты
│   │   ├── alerts.py                 # Система алертов
│   │   └── telegram_notifier.py      # Уведомления в Telegram
│   ├── web/                          # Web Dashboard
│   │   ├── app.py                    # FastAPI приложение
│   │   ├── templates/                # HTML шаблоны
│   │   │   ├── base.html            # Базовый шаблон
│   │   │   ├── dashboard.html       # Главная страница
│   │   │   └── login.html           # Страница входа
│   │   └── static/                   # Статические файлы
│   │       ├── css/style.css        # Стили
│   │       └── js/app.js            # JavaScript
│   ├── config/                       # Конфигурация
│   │   ├── manager_config.py         # Модели конфигурации
│   │   └── services.yaml             # Файл конфигурации
│   ├── utils/                        # Утилиты
│   │   └── logger.py                 # Логирование
│   └── cli.py                        # CLI интерфейс
├── bot_manager.py                    # Точка входа (обновлен)
├── manager_daemon.py                 # Daemon для dashboard
├── MANAGER_README.md                 # Полная документация
├── MANAGER_QUICKSTART.md             # Быстрый старт
└── logs/                             # Логи
    ├── manager.log
    └── dashboard.log
```

## Ключевые возможности

### 1. CLI Интерфейс (Терминал)

**Управление сервисами:**
```bash
python bot_manager.py start [service]      # Запуск
python bot_manager.py stop [service]       # Остановка
python bot_manager.py restart [service]    # Перезапуск
python bot_manager.py status               # Статус
```

**Мониторинг:**
```bash
python bot_manager.py health               # Health check
python bot_manager.py metrics              # Метрики
python bot_manager.py marzban list         # Marzban ноды
```

**Кеш:**
```bash
python bot_manager.py cache stats          # Статистика Redis
python bot_manager.py cache clear          # Очистка кеша
```

**Web Dashboard:**
```bash
python bot_manager.py dashboard            # Запуск веб-интерфейса
```

### 2. Web Dashboard (Браузер)

**Доступ:** http://your-server:8080

**Основные страницы:**
- **Dashboard** - Обзор всех сервисов, статистика
- **Services** - Детальная информация о сервисах
- **Marzban** - Инстансы и ноды
- **Metrics** - Графики и метрики

**Возможности:**
- Запуск/остановка/перезапуск сервисов одним кликом
- Реалтайм мониторинг (обновление каждые 10 сек)
- Графики метрик (CPU, память)
- Просмотр логов в реальном времени
- Аутентификация и сессии

### 3. Автоматический мониторинг

**Health Checks:**
- Автоматическая проверка здоровья сервисов каждые 30 секунд
- 4 уровня статуса: Healthy, Degraded, Unhealthy, Unknown
- Детальная информация о проблемах

**Метрики:**
- CPU usage (%)
- Memory usage (MB, %)
- Uptime
- Restart count
- Кастомные метрики для каждого сервиса

**Auto-Recovery:**
- Автоматический перезапуск упавших сервисов
- Настраиваемые политики (always, on-failure, never)
- Ограничение попыток перезапуска
- Задержка между попытками

### 4. Система алертов

**Уровни алертов:**
- INFO - Информационные сообщения
- WARNING - Предупреждения
- ERROR - Ошибки
- CRITICAL - Критические события

**Каналы уведомлений:**
- Telegram (опционально)
- Web Dashboard
- Логи

**Rate Limiting:**
- Предотвращение спама
- Минимальный интервал между одинаковыми алертами

## Архитектура

### Supervisor Pattern

```
ServiceSupervisor
    ├── TelegramBotService
    ├── MarzbanMonitorService
    ├── RedisMonitorService
    └── PostgresMonitorService

+ HealthChecker (автоматические проверки)
+ MetricsCollector (сбор метрик)
+ AlertManager (управление алертами)
```

### Service Lifecycle

1. **Регистрация** - Сервис регистрируется в супервизоре
2. **Запуск** - Supervisor запускает процесс
3. **Мониторинг** - Периодические health checks
4. **Метрики** - Сбор статистики
5. **Recovery** - Автоматический перезапуск при сбое
6. **Алерты** - Уведомления при проблемах

### Data Flow

```
Services → Metrics Collector → History Storage
         → Health Checker → Alert Manager → Telegram/Dashboard
         → Supervisor → Auto-Recovery
```

## Мониторируемые сервисы

### 1. Telegram Bot
- **Статус процесса** (tmux session)
- **PID и uptime**
- **CPU и память**
- **Логи** (real-time в dashboard)

### 2. Marzban
- **Все инстансы** из БД
- **Статус каждой ноды**
- **Количество пользователей**
- **Активные подключения**
- **Load balancing** информация

### 3. Redis
- **Latency** (ms)
- **Memory usage**
- **Total keys**
- **Hit rate** (%)
- **Connected clients**
- **Key patterns** анализ

### 4. PostgreSQL
- **Database size**
- **Active connections**
- **Query performance**
- **Table statistics**

## Конфигурация

### Основной файл: `manager/config/services.yaml`

**Основные секции:**
- `services` - Настройки каждого сервиса
- `monitoring` - Dashboard, алерты, метрики
- `logging` - Уровень и формат логирования

**Пример:**
```yaml
services:
  telegram_bot:
    enabled: true
    restart_policy: always
    max_restarts: 5

monitoring:
  web_dashboard:
    enabled: true
    port: 8080
    auth_enabled: true

  alerts:
    telegram_enabled: false
    admin_chat_ids: []
```

## Безопасность

### Аутентификация
- **Session-based** аутентификация
- **Password hashing** (SHA-256)
- **Configurable timeout**
- Защита от CSRF

### Рекомендации
1. Смените дефолтный пароль admin
2. Используйте firewall (ufw)
3. Настройте HTTPS через reverse proxy
4. Ограничьте доступ по IP
5. Регулярно ротируйте пароли

## Production Deployment

### Systemd Service

```bash
# Создать /etc/systemd/system/orbitvpn-manager.service
sudo systemctl enable orbitvpn-manager
sudo systemctl start orbitvpn-manager
```

### Nginx Reverse Proxy

```nginx
server {
    listen 80;
    server_name manager.domain.com;

    location / {
        proxy_pass http://127.0.0.1:8080;
    }
}
```

### SSL с Let's Encrypt

```bash
sudo certbot --nginx -d manager.domain.com
```

## API Endpoints

### REST API

**Authentication:**
- POST `/api/login` - Вход
- POST `/api/logout` - Выход

**Services:**
- GET `/api/status` - Общий статус
- GET `/api/services` - Информация о сервисах
- POST `/api/services/{name}/start` - Запуск
- POST `/api/services/{name}/stop` - Остановка
- POST `/api/services/{name}/restart` - Перезапуск

**Marzban:**
- GET `/api/marzban/instances` - Список инстансов
- GET `/api/marzban/instances/{id}` - Детали инстанса

**Metrics:**
- GET `/api/metrics/history` - История метрик

**Users:**
- GET `/api/users/stats` - Статистика пользователей

### WebSocket

- WS `/ws/logs/{service_name}` - Real-time логи

## Performance

### Memory Usage
- Base overhead: ~50-100 MB
- Metrics storage: Deque с max 1000 точек на сервис
- Configurable retention: 1-30 дней

### CPU Usage
- Minimal: проверки раз в 10-60 секунд
- Web requests: minimal overhead
- Efficient async/await throughout

## Troubleshooting

### Основные команды

```bash
# Проверить статус
python bot_manager.py status

# Посмотреть health
python bot_manager.py health

# Проверить логи
tail -f /root/orbitvpn/logs/manager.log

# Перезапустить сервис
python bot_manager.py restart telegram_bot
```

### Частые проблемы

1. **Dashboard не запускается** - Проверьте порт (netstat -tlnp | grep 8080)
2. **Сервисы "unknown"** - Подождите 30 секунд или запустите health check
3. **Не могу войти** - Сбросьте пароль в services.yaml
4. **Marzban не отображается** - Проверьте БД (SELECT * FROM marzban_instances)

## Расширение функционала

### Добавить новый сервис

1. Создать класс в `manager/services/your_service.py`:
```python
class YourService(ManagedService):
    async def start(self): ...
    async def stop(self): ...
    async def health_check(self): ...
    async def get_metrics(self): ...
```

2. Зарегистрировать в supervisor (manager/cli.py)

3. Добавить в конфиг (services.yaml)

### Добавить кастомные метрики

```python
metrics.custom_metrics = {
    "custom_metric": value,
    "another_metric": another_value
}
```

### Добавить алерт

```python
alert = Alert(
    level=AlertLevel.CRITICAL,
    service="your_service",
    message="Something happened"
)
await supervisor.send_alert(alert)
```

## Документация

- **MANAGER_README.md** - Полная документация
- **MANAGER_QUICKSTART.md** - Быстрый старт (5 минут)
- **MANAGER_OVERVIEW.md** - Этот файл (обзор системы)

## Команды для быстрого доступа

```bash
# Alias для удобства
alias mgr='python /root/orbitvpn/bot_manager.py'

# Использование
mgr status
mgr start telegram_bot
mgr dashboard
```

## Зависимости

Добавлены в requirements.txt:
- fastapi - Web framework
- uvicorn - ASGI server
- jinja2 - Templates
- psutil - System metrics
- pyyaml - Configuration
- click - CLI framework (уже есть)
- rich - Terminal UI (уже есть)

## Roadmap (Будущие улучшения)

- [ ] Prometheus metrics export
- [ ] Grafana dashboards
- [ ] Email alerts
- [ ] User management в dashboard
- [ ] VPN config management через UI
- [ ] Payment monitoring
- [ ] Advanced analytics
- [ ] Multi-language dashboard
- [ ] Mobile-responsive design
- [ ] Dark mode

## Поддержка

При проблемах:
1. Проверьте логи: `/root/orbitvpn/logs/`
2. Запустите диагностику: `python bot_manager.py health`
3. Проверьте конфигурацию: `manager/config/services.yaml`
4. Перезапустите сервис: `python bot_manager.py restart [service]`

---

**Версия:** 1.0.0
**Дата:** 2025-10-31
**Проект:** OrbitVPN Service Manager
