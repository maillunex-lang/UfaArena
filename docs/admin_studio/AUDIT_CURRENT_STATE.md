# Аудит текущего состояния URALIA (для Admin Studio)

Дата аудита: 2026-11-01, ветка `ccr-39bc6428-16s1r4`, коммит после `3c9be9b`. Все утверждения ниже проверены в коде,
если не помечено иначе.

## 1. Структура репозитория [Код]

| Каталог | Содержимое |
|---|---|
| `client/` | Godot-проект (Godot **4.5.1**), GDScript, ~14 500 строк в `client/src`, 5 `.tscn` |
| `server/` | FastAPI + SQLAlchemy 2 + Alembic (17 миграций, голова `0016`), Python 3.13, pytest (18 файлов тестов) |
| `admin_app/` | WebView-обёртка админки для Android (Java, сборка без Gradle), пакет `ru.uralia.admin` |
| `content_src/` | Исходники контент-пакетов (пример `fortress_autumn_fair`) |
| `docs/` | GDD, лор, AI-спецификации, community, UI-дизайн, деплой, редактор игры |
| `Continued/` | Передаточные файлы: STATE / NEXT / RULES / PATCH_LOG |
| `docker-compose.yml` | `db` (Postgres 16), `redis` (7, без персистентности), `api`, `ai-director` |
| `tools/`, `licenses/`, `ASSET_REGISTER.csv` | Вспомогательные скрипты, лицензии ассетов |

## 2. Клиент Godot [Код]

- `project.godot`: окно 1080×1920, `stretch/mode=canvas_items`, `aspect=expand`, **только портретная ориентация**
  (`handheld/orientation=1`).
- Автозагрузки: `Config`, `Api`, `Content`, `Game`, `Sfx`, `Gfx`, `Models`, `Router` (+ класс `UI`, `GameIcon`).
- **UI собирается кодом**, а не сценами: библиотека статических функций `client/src/ui/UI.gd` (46 функций: `card`,
  `button`, `icon_button`, `tile`, `chip`, `badge`, `bar`, `progress`, `tabs`, `section`, `scroll`, `state`,
  `skeleton`, `confirm`, `glass_panel`, `rewards_row`, `stars`, `rarity_tag`…). Цвета и размеры — **константы**
  (`const GOLD`, `const TEAL`, `SP`, `FS`, `R`) → сейчас не меняются в рантайме.
- Экраны: 26 скриптов `client/src/screens/*.gd`, переключение в `scenes/Main.gd` (`SCREENS`, `open()`).
- Подменяемая графика: `UI.art(path)` / `UI.skin(...)` берут PNG из контент-пакета `ui.art` (слоты админки «Графика»);
  иконки `GameIcon` подменяются `icons/<kind>.png`.
- Данные-управляемый UI: **только** нижняя панель, главный экран и «Ещё» (`Game.layout`, `ui_part()`), с 0.7.7.
- Локализация: **отсутствует** (0 вызовов `tr()`, строки на русском в коде).
- Контент-система `client/src/content/Content.gd`: подписанный манифест (RSA-SHA256), загрузка пакетов с докачкой,
  проверка SHA-256, **атомарное переключение** набора (state.json через tmp+rename), хранение предыдущего набора для
  отката, отчёт серверу (`/content/verify-install`), фоновые загрузки, kill switch, `min_client_version`.
  Разрешённые расширения: json, glb, png, jpg, jpeg, webp, ogg, txt, md. Код из пакетов не исполняется.
- `Config.CHANNEL = "dev"` — **выпущенные APK слушают канал `dev`** (важно для окружений, см. ENVIRONMENTS).
- Тестовые драйверы `client/tools/E2E*.gd` (исключены из экспорта), проверка `tools/Check.tscn`.

## 3. Сервер [Код]

- Монолит FastAPI `server/app/main.py`, префикс игрового API `/api/v1`, 266 HTTP-маршрутов.
- Модули: `modules/` (auth, game, economy, shop, content, release, story, caravan, hub, admin, health),
  `social/` (friends, guilds, alliances, raids, arena, tournaments, chat, moderation, events, rankings, progression,
  anticheat, scheduler, channels), `monetization/` (catalog, payments в тестовом режиме, vip, battlepass, analytics),
  `ai/` (Director, personality, memory, social, guild AI, outreach, play, compete, llm, adult),
  `game/` (data.py — статический контент, battle_sim.py — серверный детерминированный бой, seed.py),
  `game_editor/` (overrides, balance, campaign, layout), `admin_web/` (страница /admin, art.py), `content/`.
- БД: 105 таблиц (полный список — `server/app/models.py`). Ключевые для Studio: `server_settings` (ключ → JSON),
  `admin_actions`, `audit_events`, `content_packages`, `content_package_versions`, `content_manifest_versions`,
  `content_installations`, `shop_products`, `catalog_changes`, `analytics_events`, `job_runs`.
- Redis: только rate limiting (`core/ratelimit.py`), при отсутствии — память процесса.
- Авторизация игроков: короткий JWT + ротируемые refresh-токены (`core/security.py`).
- **Авторизация админов: один общий токен** `URALIA_ADMIN_TOKEN` в заголовке `X-Admin-Token`, имя — самозаявленное
  `X-Admin-Name` (`modules/admin.py:30`). Ролей, пользователей-админов, сессий нет. Лимит 60 запросов/мин на IP.
- Идемпотентность: `core/idempotency.py` + таблица `idempotency_keys` (для игровых мутаций).
- Фоновые задачи: планировщик внутри `api` (`social/scheduler.py`, `JOBS`, таблица `job_runs`); отдельный процесс
  `ai-director` с очередью `ai_tasks` (лизинг, повторы, идемпотентность).
- Логи: stdout (`logging`), журналы в БД: `admin_actions` (действия админов), `audit_events` (игроки),
  `ai_activity_log`. Мониторинга (Prometheus и т.п.) нет; есть `/health/live`, `/health/ready`, «Обзор» в админке.
- Конфигурации игры живут в **пяти разных местах**:
  1. код `game/data.py` (герои, кампания, призыв, здания, квесты, стартовый кошелёк…);
  2. JSON-файлы `game/content/*.json` (roster 62 КБ, social 34 КБ, monetization 38 КБ, story 2 КБ), читаются с диска;
  3. `server_settings` — разрозненные ключи (`ai_director`, `ai_speech`, `ai_tiers`, `ai_memory_settings`,
     `ai_switches`, `ai_chat_pause`, `payments_mode`, `release`, `game_overrides`, `ui_layout`, …);
  4. слой правок редактора `game_overrides` (история 50 версий, откат) поверх `data.py`;
  5. контент-пакеты (клиентские ассеты и `core.balance`).
- Версионирование сейчас: каждое место по-своему (Section-история для AI, история `game_overrides` и `ui_layout`,
  `catalog_changes` с revert для магазина, неизменяемые манифесты для контента). Единого реестра нет.

## 4. Существующая админка [Код]

- `/admin` — одна HTML-страница `admin_web/admin.html` (~740 строк, ванильный JS): Обзор, Сервер и APK, События,
  Чат, Игроки и модерация, ИИ-жители (14 подразделов), Редактор игры (Герои, Баланс, Кампания, Редактор карты,
  Интерфейс, История), Графика (слоты PNG/GLB → публикация пакетов `ui.art` / `ui.models3d`), Магазин.
- `/admin/shop` — отдельная страница монетизации (`monetization/admin.html`).
- API: `/admin/api/*`, `/admin/api/web/*`, `/admin/api/ai/*`, `/admin/api/game/*`, `/admin/api/social/*`.
- Публикация в игру сейчас **мгновенная** (кроме контент-пакетов): сохранил → действует. Нет DRAFT/APPROVAL.
- Приложение `admin_app/` — тонкая WebView-обёртка над `/admin` (1.0).

## 5. Деплой [Код][Док]

Один VPS (1 vCPU, 2 ГБ RAM, общий с другими проектами), `docker compose` в `/opt/uralia`; TLS не настроен (HTTP на
:8000); обновление — `git pull && docker compose up -d --build`; миграции Alembic при старте. Окружение одно.
Каналы контента `dev | test | beta | stable` существуют в коде (`content/service.py`: promote, activate, kill switch).

## 6. Таблица систем

Состояние: ✅ есть и работает · 🟡 частично · ❌ отсутствует. Интеграция: насколько легко подключить к Studio.

| Система | Найденная реализация | Технология | Состояние | Возможность интеграции |
|---|---|---|---|---|
| Игровые механики (переключатели) | `ai_switches`, `payments_mode`, kill switch контента | server_settings JSON | 🟡 | Высокая: обернуть в реестр |
| Баланс героев | `data.py` HEROES + `game_overrides` + отчёт `game_editor/balance.py` | Python + JSON | ✅ | Высокая: уже есть слой правок |
| Экономика (кошелёк, цены, награды) | `data.py` (STARTING_WALLET, QUESTS…), `monetization.json`, `shop_products` | Python/JSON/БД | 🟡 | Средняя: вынести константы в конфиг |
| Персонажи (герои) | `heroes`, редактор героев | БД + overrides | ✅ | Высокая |
| Фракции, классы | `factions`, `classes` из `roster.json` | JSON → БД | 🟡 (без редактора) | Средняя |
| Способности (kits) | `roster.json` kits, battle_sim v3 | JSON + Python | 🟡 (редактор — поле JSON) | Средняя: нужна схема kits |
| Враги и боссы | `RAID_BOSSES`, enemy-герои, отряды `_SQUADS` | Python | 🟡 | Средняя |
| Предметы и экипировка | плитки «Экипировка/Артефакты — скоро» | — | ❌ | Требует новой игровой системы (код) |
| Выпадение предметов | награды этапов, `raid_loot`, призыв `SUMMON_POOLS` | Python + БД | 🟡 | Средняя (пулы призыва — конфиг) |
| Прогрессия | уровни, звёзды (`SHARDS_PER_STAR`…), VIP, battle pass, `progression.py` | Python/JSON | 🟡 | Средняя |
| Кампания и локации | регионы/этапы + редактор кампании и карты | БД + overrides | ✅ | Высокая |
| PvP | arena, tournaments (`social.json`) | Python/JSON | 🟡 (без редактора) | Средняя |
| События и задания | world events (`social.json` шаблоны), quests (`data.py`) | JSON/Python | 🟡 (запуск событий в админке) | Средняя |
| Магазины и предложения | `shop_products`, `catalog_changes` (revert), лавка | БД | ✅ (/admin/shop) | Высокая |
| Награды и ежедневка | quests, daily_activity, battle pass, VIP | Python/JSON | 🟡 | Средняя |
| AI Living Community | Director, 14 разделов админки, Section-история | Python + server_settings | ✅ | Высокая (Section ≈ мини-реестр) |
| Чаты и социалка | chat, moderation, guilds, alliances, `social.json` | Python/JSON | ✅ (модерация в админке) | Средняя |
| Игровой интерфейс | `UI.gd` кодом; `ui_layout` для 3 экранов | GDScript + JSON | 🟡 | **Низкая**: нужен UI-рантайм по схеме |
| Визуальные ресурсы | слоты «Графика» → пакеты `ui.art`, `ui.models3d` | content packages | ✅ | Высокая |
| Анимации и эффекты | `looks/*.json` (маппинг анимаций GLB, масштаб), `Gfx.gd` | JSON + GDScript | 🟡 | Средняя (только параметры) |
| Звуки | `Sfx.gd`, ogg в пакетах | content packages | 🟡 | Средняя |
| Локализация | нет | — | ❌ | Требует кода (ключи строк) |
| Сегменты игроков | нет (только VIP-уровни, возраст D-C1) | — | ❌ | Новая подсистема |
| Эксперименты / Feature Flags | переключатели без таргетинга; каналы контента | JSON | 🟡 | Средняя |
| Аналитика | `analytics_events` (монетизация), «Обзор», графики AI | БД | 🟡 | Средняя |
| Мониторинг | `/health`, `job_runs`, статус Director | — | 🟡 | Средняя |
| Обновления клиента | `release` + `/downloads` + окно «Вышло обновление» | server_settings + файлы | ✅ | Высокая |
| Контент-доставка | манифесты, подписи, каналы, откат, verify-install | БД + RSA | ✅ | **Высокая — основа Studio** |
| Админ-авторизация | один общий токен | заголовок | 🟡 (небезопасно для команды) | Требует новой подсистемы |
| Аудит | `admin_actions` (без сравнения версий) | БД | 🟡 | Высокая |

## 7. Главные выводы аудита

1. **Готовая основа доставки** [Код]: неизменяемые подписанные манифесты, каналы, активация/откат, атомарное
   применение и отчёт клиента — это уже половина жизненного цикла PUBLISHED → ACTIVE → APPLIED для клиентских данных.
2. **Конфигурации разбросаны** [Код] по коду, JSON-файлам и десяткам ключей `server_settings` — главное, что
   решает Configuration Registry.
3. **UI не схемный** [Код]: полноценный Pro-редактор требует нового UI-рантайма в Godot и переноса экранов по одному.
4. **Безопасность админки — общий токен** [Код]: для команды и опасных операций нужна новая модель (роли, сессии).
5. **Одно окружение и APK на канале dev** [Код]: STAGING/PRODUCTION нужно вводить аккуратно (решение владельца).
6. **Ресурсы сервера малы** [Док]: 1 vCPU / 2 ГБ — тяжёлую работу (сборка пакетов, рендер превью) делать дозированно.
