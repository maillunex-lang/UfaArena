# Интеграция с сервером

Базовый адрес: `Config.server_url` + `/api/v1`. Все изменяющие запросы идут с ключом идемпотентности (`Api.post_json(..., true)`).

## Эндпоинты, которые использует новый интерфейс
| Экран | Метод |
|---|---|
| Главная, колокольчик, бейджи | `GET /player/summary` (новый, read-only агрегат; обновление раз в 45 с) |
| Дозор | `POST /rewards/afk/claim` |
| Задания | `GET /quests`, `POST /quests/{code}/claim`, `GET /progression`, `GET /guilds/mine`, `POST /guilds/tasks/{code}/claim` |
| Центр гильдии | `GET /guilds/mine`, `GET /raids`, `GET /rankings/guilds`, `GET /guilds/shop` (новый), `POST /guilds/shop/{code}/buy` (новый) |
| Профиль | `GET /social/profile/{user_id}`, `GET /progression` |
| Настройки → аккаунт | `POST /player/nickname`, `POST /auth/link` (+`recovery_code` в ответе), `POST /auth/recovery-code` (новый), `POST /auth/password` (новый), `POST /auth/logout` |
| Вход | `POST /auth/guest`, `POST /auth/login`, `POST /auth/recover` (новый), `POST /auth/refresh` |
| ИИ-жители | `GET/POST /social/ai-prefs` |

## Авторизация и синхронизация
* Гость (устройство) → привязка email + пароль (URALIA ID) → вход с любого устройства; прогресс хранится на сервере.
* Восстановление доступа: одноразовый **код восстановления** (выдаётся при привязке email и в настройках, хранится только
  scrypt-хэш). `POST /auth/recover` ставит новый пароль, выходит со всех устройств и выдаёт новый код.
  Отправка писем не используется: SMTP на сервере нет.
* Других способов входа (Google, VK, Apple, Telegram) нет — по ТЗ.

## Магазин гильдии
Товары — `server/app/game/content/social.json` → `guilds.shop`. Недельный лимит считается по неизменяемому журналу
кошелька (`reason="guild_shop"`, `ref="<код>:<неделя>"`), поэтому новых таблиц нет.

## Web-версия
Сервер раздаёт экспорт Godot Web на `/play`, если в `URALIA_WEB_CLIENT_PATH` (по умолчанию `server/var/web`,
в docker — `./web`) лежит `index.html`. Клиент в браузере обращается к API своего же адреса (`window.location.origin`).

## Платежи
Без изменений: тестовый режим по умолчанию, реальные транзакции заблокированы сервером.
