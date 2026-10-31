# УРАЛИЯ: Дыхание предков

Оригинальная коллекционная онлайн AFK RPG для Android (портрет 9:16). Фэнтезийная вселенная, художественно связанная с Башкортостаном и Уралом.
Проектная документация лежит в [`docs/design/`](docs/design/), отчёты по блокам — в [`docs/reports/`](docs/reports/).

![Обзор](docs/screenshots/overview.jpg)

## Структура
```
client/   Godot 4.5 — Android-клиент (Mobile renderer)
  src/autoload   Config, Api (сеть/ретраи/идемпотентность), Game (кэш состояния), Sfx, Gfx (адаптивная графика), Models, Router
  src/world      HubWorld (Крепость хранителей), CampaignMap (карта региона), Arena (изометрическая арена + VFX)
  src/scenes     Boot (манифест → вход → bootstrap), Main (оболочка UI), Battle (воспроизведение серверного боя)
  src/screens    Home, Campaign, Heroes, Formation, Summon, Fortress, Quests, Mail, Modes, Settings
  src/content    ContentUpdater — клиент Uralia Update System
  src/ui         Liquid Glass UI: шейдер стекла, кит компонентов, векторные иконки, диалоги с портретами
  tools/         dev-инструменты: E2E-драйвер UI, скриншоты, проверка компиляции (в APK не входят)
server/   Python 3.13 + FastAPI — модульный монолит
  app/core       конфиг, БД, JWT + ротация refresh, rate limit, идемпотентность, аудит, подпись манифестов
  app/game       статические данные (герои, кампания, экономика), детерминированная симуляция боя, сид
  app/modules    auth, game (профиль/герои/формация/бой/кампания), economy (призыв/AFK/крепость/задания/почта), content, health
  alembic/       миграции PostgreSQL
  scripts/       backup / restore / проверка восстановления
  tests/         pytest: полный игровой цикл, безопасность, гонки двойной выдачи, детерминизм боя
tools/gen_music.py   генератор оригинальной музыки (мотивы курая)
ASSET_REGISTER.csv   реестр ассетов и лицензий; подтверждения — в licenses/
```

## Быстрый старт

### Сервер
```bash
cd server
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q                       # тесты на SQLite
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000   # dev: SQLite + автосид
```
PostgreSQL:
```bash
export URALIA_DATABASE_URL=postgresql+psycopg://uralia:PASS@localhost:5432/uralia
.venv/bin/alembic upgrade head && .venv/bin/uvicorn app.main:app --port 8000
URALIA_DATABASE_URL=... .venv/bin/python -m pytest -q   # включает тесты параллельной выдачи наград
```
Docker (нужен Docker daemon): `URALIA_DB_PASSWORD=... URALIA_JWT_SECRET=... docker compose up --build`.
Swagger UI в dev: http://localhost:8000/docs

### Клиент
- Откройте `client/` в Godot 4.5.1 и запустите сцену по умолчанию (Boot).
- Адрес сервера по умолчанию: `http://127.0.0.1:8000` на ПК и `http://10.0.2.2:8000` на эмуляторе Android. Меняется в «Профиль и настройки» или через переменную `URALIA_SERVER_URL`.
- Сборка APK (вручную): Project → Export → Android, или
  `godot --headless --path client --export-debug "Android" ../build/uralia-debug.apk`
  (в настройках редактора нужны Android SDK, JDK 17+ и debug keystore).
- E2E-прогон UI против запущенного сервера: `URALIA_E2E=/путь/к/папке/скриншотов godot --path client`.

## Принципы
- Сервер — источник истины для валют, призывов, AFK, прогресса и наград. Клиент только отображает результат.
- Валюты меняются транзакционно, каждое изменение пишется в неизменяемый ledger `wallet_transactions`. Все выдачи наград защищены `Idempotency-Key`.
- В APK нет секретов backend. Клиент хранит только публичный ключ для проверки подписанных манифестов (в dev-канале ключ пока запрашивается при первом запуске, TOFU).
- Ассеты используются только с проверенной лицензией (см. `ASSET_REGISTER.csv`). Ассеты коммерческих игр не используются.
