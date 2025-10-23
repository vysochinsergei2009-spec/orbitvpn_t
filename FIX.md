При создании конфига пишет что выбрана нода S002:

[2025-10-22 19:15:10,292] INFO in app.repo.marzban_client: Selected node S002 (ID: 1) on instance s001 with load score 0.00
[2025-10-22 19:15:10,334] INFO in app.repo.marzban_client: Created user orbit_7559373710 on instance s001 (target node: 1)
[2025-10-22 19:15:10,417] INFO in app.repo.marzban_client: Selected node S002 (ID: 1) on instance s001 with load score 0.00
[2025-10-22 19:15:10,431] INFO in app.repo.user: Config created for user 7559373710 on Marzban instance s001
[2025-10-22 19:15:10,502] INFO in aiogram.event: Update id=705045272 is handled. Duration 631 ms by bot id=8461779178
[2025-10-22 19:15:11,835] INFO in aiogram.event: Update id=705045273 is handled. Duration 166 ms by bot id=8461779178

но при этом IP адрес не соответствует ноде S002 и выдает ссылку с конфигом на S001 (главный сервер)

нужно чтоб на главном сервере не было юзеров впн, только на нодах.