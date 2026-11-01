# Развёртывание сервера УРАЛИИ на VPS

Схема: Docker Compose поднимает 3 контейнера — PostgreSQL 16 (данные), Redis 7 (лимиты запросов) и API (FastAPI).
При старте API сам применяет миграции и заполняет игровые данные.
Ориентир: Ubuntu 22.04/24.04 или Debian 12, от 1 ГБ RAM (лучше 2 ГБ), 10 ГБ диска.

## 0. Подключиться
Termius → хост `144.31.254.99`, пользователь `root` (или ваш), порт 22. Все команды ниже выполняются в этом терминале.

```bash
cat /etc/os-release      # должно быть Ubuntu или Debian
free -h; df -h /         # память и диск
```

## 1. Обновить систему и поставить Docker
```bash
apt update && apt -y upgrade
apt -y install ca-certificates curl git ufw
curl -fsSL https://get.docker.com | sh
docker --version && docker compose version
```

## 2. Файрвол
```bash
ufw allow OpenSSH
ufw allow 8000/tcp        # API игры (пока без домена)
ufw allow 80/tcp          # пригодится для HTTPS (шаг 7)
ufw allow 443/tcp
ufw --force enable
ufw status
```
⚠️ Не закрывайте SSH: `ufw allow OpenSSH` обязательно до `enable`.
Учтите: порты, опубликованные Docker, проходят мимо ufw. Поэтому в шаге 7 API привязывается к `127.0.0.1`.

## 3. Скачать код
Код лежит в ветке `ccr-39bc6428-16s1r4`.
```bash
cd /opt
git clone -b ccr-39bc6428-16s1r4 https://github.com/maillunex-lang/UfaArena.git uralia
cd /opt/uralia
```
Если репозиторий приватный, git спросит логин и пароль. Вместо пароля вводится
**Personal Access Token**: GitHub → Settings → Developer settings → Fine-grained tokens, доступ только
к этому репозиторию, право Contents: Read-only.

## 4. Секреты
```bash
cd /opt/uralia
cp .env.example .env
sed -i "s/^URALIA_DB_PASSWORD=.*/URALIA_DB_PASSWORD=$(openssl rand -hex 24)/" .env
sed -i "s/^URALIA_JWT_SECRET=.*/URALIA_JWT_SECRET=$(openssl rand -hex 32)/" .env
chmod 600 .env
cat .env
```
Пароли состоят только из hex-символов, иначе они ломают строку подключения к БД. Файл `.env` никуда не публикуйте.
`URALIA_ENV=dev` оставьте на время закрытого теста: Swagger будет доступен по `/docs`, а ключ подписи
контента сгенерируется сам.

## 5. Запуск
```bash
docker compose up -d --build      # первая сборка — 2–5 минут
docker compose ps                 # все три сервиса должны быть Up, db — healthy
docker compose logs -f api        # Ctrl+C — выйти из логов
```
В логах должно быть `Running upgrade -> 0001, initial schema` и `Uvicorn running on http://0.0.0.0:8000`.

Проверка на самом сервере и с вашего компьютера/телефона:
```bash
curl http://127.0.0.1:8000/health/ready        # {"status":"ready"}
```
Откройте в браузере `http://144.31.254.99:8000/health/ready` и `http://144.31.254.99:8000/docs`.

## 6. Подключить игру
В текущем APK сервер по умолчанию уже `http://144.31.254.99:8000`: установите APK и запускайте.
Если адрес изменится, на экране «Нет связи» есть поле адреса и кнопка «Сохранить».
Позже адрес меняется в «Профиль и настройки» → «Сервер».

## 7. HTTPS (обязательно до открытой беты)
Нужен домен (например, `api.uralia.ru`) с A-записью на `144.31.254.99`.
```bash
apt -y install caddy
cat > /etc/caddy/Caddyfile <<'EOF'
api.ВАШ-ДОМЕН {
    reverse_proxy 127.0.0.1:8000
}
EOF
systemctl reload caddy
# API теперь доступен только через Caddy:
sed -i 's/^URALIA_API_BIND=.*/URALIA_API_BIND=127.0.0.1:8000/' /opt/uralia/.env
cd /opt/uralia && docker compose up -d
ufw delete allow 8000/tcp
```
Caddy сам получает и продлевает сертификат Let's Encrypt. В игре адрес становится `https://api.ВАШ-ДОМЕН`.

## 8. Бэкапы
```bash
mkdir -p /opt/uralia-backups
cat > /etc/cron.d/uralia-backup <<'EOF'
30 3 * * * root cd /opt/uralia && docker compose exec -T db pg_dump -U uralia -Fc uralia > /opt/uralia-backups/uralia_$(date +\%F).dump && find /opt/uralia-backups -name '*.dump' -mtime +14 -delete
EOF
# проверить вручную:
cd /opt/uralia && docker compose exec -T db pg_dump -U uralia -Fc uralia > /opt/uralia-backups/test.dump && ls -lh /opt/uralia-backups
```
Восстановление (затирает текущие данные!):
```bash
docker compose exec -T db pg_restore -U uralia -d uralia --clean --if-exists < /opt/uralia-backups/ФАЙЛ.dump
```
Копируйте бэкапы и за пределы VPS (например, `scp` на свой компьютер или в объектное хранилище).

## 9. Обновление сервера
```bash
cd /opt/uralia && git pull && docker compose up -d --build && docker compose logs --tail=50 api
```
Данные БД лежат в Docker-томе `pgdata` и при обновлении не теряются.
Никогда не выполняйте `docker compose down -v`: флаг `-v` удаляет базу.

## Частые проблемы
| Симптом | Что делать |
|---|---|
| `set URALIA_DB_PASSWORD` при запуске | Нет файла `.env` или он лежит не в `/opt/uralia` |
| API в цикле перезапускается | `docker compose logs api`: обычно ошибка подключения к БД (неверный пароль после смены `.env`, а том БД создан со старым паролем) |
| С телефона не открывается, на сервере `curl` работает | Порт закрыт у хостера (панель VPS → firewall) или в ufw |
| Сборка падает по памяти на 1 ГБ RAM | Добавьте swap: `fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile` |
| Нужно посмотреть БД | `docker compose exec db psql -U uralia uralia` |

## 10. Обновление до 0.2 (система обновлений контента + бой в реальном времени)
```bash
cd /opt/uralia && git pull && docker compose up -d --build && docker compose logs --tail=50 api
```
Миграция `0002` применится автоматически (новая таблица версий пакетов, колонка VIP).
Старый манифест будет перевыпущен с пакетом `core.balance` в хранилище контента.

## 11. Публикация контента без обновления APK
Пакет — это папка с `package.json` и ассетами. Разрешены только данные: `.glb .png .jpg .webp .ogg .json .txt`.
Скрипты, сцены и библиотеки отклоняются. Исходники пакетов лежат в `content_src/` и смонтированы в контейнер.
```bash
A="docker compose exec api python -m app.content.admin"
$A publish /srv/content_src/fortress_autumn_fair --channel dev --notes "Осенняя ярмарка"
$A list --channel dev                 # история манифестов, * = активный
$A activate 1 --channel dev           # откат на манифест v1 (или обратно на новый)
$A remove fortress.autumn_fair        # убрать пакет
$A kill on | off                      # аварийно отключить весь контент (клиенты вернутся к встроенному)
$A promote dev beta                   # перенести набор пакетов в другой канал
$A min-client 0.3.0                   # потребовать новый APK (только если менялся код)
$A set-vip UR-XXXXXXXX 3              # тест: выдать VIP 3 (ускорение до x6)
```
Клиенты проверяют манифест при запуске и раз в 15 минут во время игры. Новые пакеты скачиваются
в фоне с докачкой и применяются, когда игрок возвращается на экран крепости.
Чтобы выпустить новую версию пакета, увеличьте `"version"` в его `package.json`.

## 12. Монетизация (тестовый режим) и панель владельца
> Если в игре магазин или пропуск отвечают «Ошибка сервера (404)», а `/admin` — `{"detail":"Not Found"}`,
> на VPS работает старая версия сервера. Обновите её:
> ```bash
> cd /opt/uralia && git pull && docker compose up -d --build && docker compose logs --tail=30 api
> ```

Реальные платежи выключены. Все покупки в игре тестовые: товар выдаётся, деньги не списываются.
Включить панель `/admin`:
```bash
cd /opt/uralia
grep -q URALIA_ADMIN_TOKEN .env || echo "URALIA_ADMIN_TOKEN=$(openssl rand -hex 24)" >> .env
docker compose up -d
grep URALIA_ADMIN_TOKEN .env      # этот токен вводится на странице
```
Откройте `http://144.31.254.99:8000/admin` и введите токен. В панели: каталог и цены, скидки (до 35%), журнал изменений
с откатом, заказы и возвраты, споры, промокоды, аналитика, режим платежей. Подробнее — `docs/MONETIZATION.md`.

## 13. Онлайн-системы (чат, друзья, ИИ-жители) — обновление сервера 0.6
Миграция 0005 только добавляет таблицы и колонки. Перед обновлением сделайте бэкап:
```bash
cd /opt/uralia
docker compose exec db pg_dump -U uralia uralia > backup_before_0005.sql
git pull
docker compose up -d --build
docker compose logs --tail=40 api
```
После старта фоновые задачи сервера сами создадут ИИ-жителей (около 30, с меткой «ИИ») и виртуальные гильдии.
Состояние задач и ИИ — в `/admin` (вкладка API) или: `curl -H "X-Admin-Token: <токен>" http://144.31.254.99:8000/admin/api/social/overview`.

## 14. Окно «Вышло обновление» и загрузка APK с сервера
Клиент при входе спрашивает `/api/v1/client/release`. Если на сервере опубликована более новая версия,
игрок видит окно со списком изменений и кнопкой «Скачать» (страница `http://144.31.254.99:8000/download`).

Как опубликовать новый APK:
1. В Termius откройте SFTP к серверу и загрузите APK в папку `/opt/uralia/downloads/` (например `uralia-0.6.0.apk`).
2. Создайте `/opt/uralia/downloads/release.json` (образец — `downloads/release.example.json`):
```json
{"version": "0.6.0", "min_version": "0.5.0", "file": "uralia-0.6.0.apk", "url": null,
 "title": "Онлайн-обновление", "notes": ["Чат", "Друзья", "ИИ-жители"]}
```
3. Перезапуск не нужен — файл читается при каждом запросе (папка подключена в контейнер только для чтения).

`min_version` — версии ниже неё получат обязательное окно без кнопки «Позже». Вместо своего сервера можно
указать внешнюю ссылку в `url` (например, страницу в RuStore) — тогда кнопка «Скачать» откроет её.


## 15. Веб-админка `/admin`
Откройте `http://144.31.254.99:8000/admin` и войдите токеном (`grep URALIA_ADMIN_TOKEN /opt/uralia/.env`).
Разделы: Обзор (игроки, онлайн, ИИ, фоновые задачи), Сервер и APK (переключатели ИИ, выпуск и загрузка APK,
окно «Вышло обновление»), События (запуск и завершение мировых событий, новый рейд-босс, турнир, подарок-письмо всем),
Чат (сообщения от имени администрации, скрытие сообщений), Игроки и модерация (поиск, санкции, VIP-опыт, жалобы,
апелляции, античит), Графика (замена портретов, иконок, оформления чата, фонов: совет, промпт, загрузка PNG,
кнопка «Опубликовать» — игроки получают графику фоновым обновлением без нового APK, нужна версия игры 0.6.3+),
Магазин (прежняя панель монетизации, теперь по адресу `/admin/shop`).

Чтобы загрузка APK из админки могла записывать файлы, один раз выполните:
```bash
cd /opt/uralia
mkdir -p downloads
docker compose up -d --build
docker compose exec -u root api chown -R uralia /srv/var/downloads
```

## 16. Где скачивать APK
Готовые сборки выкладываются в ветку `apk` репозитория (только файл APK, без истории версий):
https://github.com/maillunex-lang/UfaArena/raw/apk/uralia-latest.apk
APK собирается только под ARM64 (все современные телефоны), поэтому весит около 50 МБ.
Эту же ссылку можно указать в админке («Сервер и APK» → «Внешняя ссылка»), чтобы окно
«Вышло обновление» в игре вело прямо на GitHub.

## 17. Обновление 0.7: новый интерфейс, восстановление доступа, магазин гильдии, Web-версия
Миграция 0008 только добавляет колонку `users.recovery_hash`. Перед обновлением — бэкап:
```bash
cd /opt/uralia
docker compose exec db pg_dump -U uralia uralia > backup_before_0008.sql
git pull
docker compose up -d --build
docker compose logs --tail=40 api        # должно быть: Running upgrade 0007 -> 0008
```
Новый APK 0.7.0: ссылка из раздела 16 (ветка `apk`) или загрузка в `/admin` → «Выпуски», чтобы игроки увидели окно обновления.

**Web-версия (по желанию).** Скопируйте папку экспорта Web (`index.html`, `index.js`, `index.wasm`, `index.pck` и др.)
в `/opt/uralia/web/` и выполните `docker compose up -d`. Игра откроется по адресу `http://144.31.254.99:8000/play/`.
Без файлов маршрут `/play` просто не подключается. Подробности сборки — `docs/ui/build.md`, откат — `docs/ui/rollback.md`.
