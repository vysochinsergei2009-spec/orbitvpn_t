- Add YooKassa payment method
- Improve Bot_Manager program and fix bugs in it
- Completely change the website
- Adblocker
- New web Hosts


● Записал! Вот краткое резюме где мы остановились:

  Текущая ситуация:

  Проблема: Сайт не открывается, ошибка 520 от Cloudflare

  Причина: Xray от Marzban занимает порт 443, nginx не может на него встать

  Что узнали:
  - Nginx сейчас на порту 2053 (временно)
  - Xray PID 1395711 (управляется Marzban) слушает порт 443
  - Xray PID 690921 - тестовый, на порту 8080
  - Marzban работает в Docker контейнере marzban-marzban-1
  - Конфиг xray передается через stdin от Marzban

  Решение (выбрали вариант 1):
  Настроить nginx как reverse proxy с fallback на xray:
  1. Переместить Marzban xray с 443 на 8443
  2. Nginx поставить на 443
  3. Nginx проксирует VPN трафик → xray:8443
  4. Обычный веб-трафик обрабатывает nginx

  Что нужно сделать завтра:
  - Найти где Marzban хранит конфиг xray
  - Изменить порт 443→8443 в Marzban
  - Настроить nginx fallback на xray