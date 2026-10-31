Положите сюда `content_public_key.pem` — публичный ключ подписи манифестов канала (beta/stable).
Получить: `curl https://<server>/api/v1/content/public-key > content_public_key.pem`.
Без файла клиент dev-канала запрашивает ключ при первом запуске (TOFU) — только для разработки.
Приватный ключ никогда не кладётся в клиент.
