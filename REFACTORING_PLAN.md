# OrbitVPN Refactoring Plan

**Цель**: Переход от жесткой привязки к Marzban к гибкой, расширяемой архитектуре с поддержкой нескольких VPN панелей через паттерны Strategy и Factory.

## Все задачи рефакторинга

| № | Задача | Статус | Issue |
|---|--------|--------|-------|
| 1 | Base Abstraction (BaseVPNPanel, PanelUser, PanelConfig) | Открыта | [#1](https://github.com/vysochinsergei2009-spec/orbitvpn_t/issues/1) |
| 2 | Client Adapters (MarzbanPanel, MarzneshinPanel) | Открыта | [#2](https://github.com/vysochinsergei2009-spec/orbitvpn_t/issues/2) |
| 3 | Factory Pattern (PanelFactory в app/api/manager.py) | Открыта | [#3](https://github.com/vysochinsergei2009-spec/orbitvpn_t/issues/3) |
| 4 | Integration (Обновить UserRepository и config.py) | Открыта | [#4](https://github.com/vysochinsergei2009-spec/orbitvpn_t/issues/4) |
| 5 | Testing & Documentation | Открыта | [#5](https://github.com/vysochinsergei2009-spec/orbitvpn_t/issues/5) |

## Ключевые улучшения

✅ **До**: Жесткая привязка к Marzban в `app/db/user.py`  
✅ **После**: Динамический выбор панели через `PanelFactory`

✅ **До**: Дублирование логики в payment gateway  
✅ **После**: Единая система валидации через базовый интерфейс

✅ **До**: Добавление новой панели = переписывание UserRepository  
✅ **После**: Просто наследуем от `BaseVPNPanel` и регистрируем в factory

## Быстрый старт

1. Прочитайте описание каждой задачи в Issues #1-#5
2. Для полного кода - откройте **PROMPT.md** в корне репо
3. Выполняйте задачи по порядку: #1 → #2 → #3 → #4 → #5

**Документация**: Все детали в [PROMPT.md](./PROMPT.md)
