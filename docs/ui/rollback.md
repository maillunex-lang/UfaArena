# Откат

## Точка до редизайна
* Git-тег `pre-ui-redesign` → коммит `acfd825f911f3101c2f6be764c5f3ee6c21b187d` (последняя версия до редизайна, клиент 0.6.4).
* APK 0.6.4 остаётся в истории ветки `apk` (предыдущий коммит файла `uralia-latest.apk`).

## Откат клиента
```bash
git checkout pre-ui-redesign -- client      # вернуть старый клиент в рабочее дерево
# собрать APK по docs/ui/build.md и выложить как uralia-latest.apk
```
Старый клиент совместим с новым сервером: существующие контракты не менялись (новые эндпоинты он просто не вызывает,
лишнее поле `recovery_code` в ответе `/auth/link` игнорируется).

## Откат сервера
1. Бэкап: `docker compose exec db pg_dump -U uralia uralia > backup_before_0008.sql`.
2. Откат миграции 0008 (удаляет только колонку `users.recovery_hash`, выданные коды восстановления перестанут работать):
   `docker compose exec api alembic downgrade 0007`.
3. Вернуть код сервера: `git checkout pre-ui-redesign -- server docker-compose.yml`, затем `docker compose up -d --build`.
   Внимание: Dockerfile при старте выполняет `alembic upgrade head`, поэтому шаг 2 нужен только вместе с шагом 3.
4. Покупки в магазине гильдии остаются в журнале кошелька (данные не теряются).

## Web-версия
Удалить содержимое `/opt/uralia/web/` и перезапустить `api` — маршрут `/play` перестанет подключаться.
