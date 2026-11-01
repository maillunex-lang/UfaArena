# URALIA Living World AI — API

## Существующие маршруты, связанные с ИИ
| Маршрут | Кто | Назначение |
|---|---|---|
| `GET /api/v1/social/ai-prefs` | игрок | Свои настройки по отношению к ИИ + глобальные переключатели |
| `POST /api/v1/social/ai-prefs` | игрок | «ИИ атакуют мою защиту», «показывать ИИ в чате» |
| `POST /api/v1/guilds/ai-policy` | глава гильдии | Политика гильдии к ИИ (набор, офицеры, рейды, войны) |
| `GET /admin/api/social/ai-switches` | админ (токен) | Глобальные переключатели ИИ |
| `POST /admin/api/social/ai-switches` | админ | Изменить переключатели (журналируется) |
| `GET /admin/api/social/overview` | админ | Обзор: игроки, ИИ, популяция, последние действия |
| `GET /admin/api/social/jobs`, `POST …/jobs/{name}/run` | админ | Состояние и ручной запуск задач планировщика (`ai_tick`, `ai_population`) |
| `GET /api/v1/rankings/ai` | игрок | Отдельный рейтинг ИИ-персонажей |

## Реализовано в фазе 2 (`/admin/api/ai/*`, заголовок `X-Admin-Token`)
| Маршрут | Назначение |
|---|---|
| `GET /director` | Настройки, режимы, пределы, состояние (сердцебиение, такт, бюджет, очередь), владеет ли Director миром |
| `POST /director` | Изменить настройки/режим (проверка пределов, журнал, предыдущая версия сохраняется) |
| `POST /director/rollback` | Откат к предыдущей версии настроек |
| `GET /tasks?status=&kind=&limit=` | Очередь задач и счётчики по статусам |
| `POST /tasks/{id}/retry` | Повторить неудачную/отменённую задачу |
| `GET /schedules`, `PUT /schedules/{code}` | Профили расписаний (с числом ИИ в каждом); создать/изменить профиль |
| `GET /population` | Реестр, отключённые, активные сейчас, реальные игроки и онлайн, разбивка по расписаниям и архетипам |
| `POST /characters/{persona_id}/run?action=` | Ручной запуск персонажа: короткая сессия + задача с наивысшим приоритетом |
| `GET /characters?query=&only=session\|disabled&limit=` | Список ИИ-персонажей: ник, UR-номер, характер, стиль, уровень, сила, расписание, в игре ли, действий сегодня |
| `POST /characters/{persona_id}/active` | Пауза / возврат персонажа (не удаляется, прогресс сохраняется; журналируется) |
| `GET /activity?limit=` | Последние действия ИИ (журнал живого мира) |

**Интерфейс:** вкладка «ИИ-жители» в действующей админ-панели `/admin` (тот же вход по токену): Director (состояние,
режим, настройки, откат), переключатели ИИ (перенесены из «Сервер и APK»), персонажи (поиск, пауза, ручной запуск),
расписания (редактирование), очередь задач (фильтр, повтор), журнал действий. Отдельной панели нет.

## Реализовано в фазе 3
| Маршрут | Назначение |
|---|---|
| `GET /settings/{speech\|memory\|tiers}`, `POST …`, `POST …/rollback` | Настройки речи (с состоянием локальной модели), памяти, слоёв силы (с описанием слоёв, распределением и уровнем мира); проверка, журнал, откат |
| `GET /archetypes`, `PUT /archetypes/{code}` | Архетипы как данные (+ справочники черт, амбиций, привычек) |
| `GET /characters/{id}` | Карточка: профиль, слой, тактика, характер, счётчики, память, биография, контрольные точки, архив |
| `PATCH /characters/{id}` | Правка характера (черты, амбиции, привычки, настроение, слой, темп, стиль, предыстория); сначала — контрольная точка |
| `POST /characters/{id}/checkpoint`, `POST /characters/{id}/restore/{snapshot_id}` | Контрольная точка; восстановление характера (прогресс не трогается) |
| `GET /characters/{id}/export`, `POST /characters/{id}/import` | Перенос профиля (формат `uralia-ai-persona/1`) |
| `GET /memory/search?q=&kind=&persona_id=`, `PATCH /memory/{id}` | Поиск по памяти; правка (старое значение — в журнале) |
| `GET /memory/stats`, `POST /memory/archive-now` | Объём памяти; архивация вручную |

## Реализовано в фазе 4
**Игровое API (`/api/v1`, для всех игроков):** `GET /alliances/mine`, `POST /alliances/propose`,
`POST /alliances/proposals/{id}/{accept|decline|cancel}`, `POST /alliances/leave`, `POST /alliances/rename`;
`GET /chat/channels` теперь возвращает и каналы `news`, `region:*`, `event:*`, `alliance:*`, `group:*` (поле `kind`,
у `news` — `read_only`); `POST /social/ai-prefs` принимает `ai_contact`.

**Админ-API (`/admin/api/ai/*`):**
| Маршрут | Назначение |
|---|---|
| `GET/POST /settings/{channels\|guilds\|outreach}` (+ `/rollback`) | Каналы и участие ИИ, гильдии ИИ, общение с игроками |
| `GET /social/overview`, `POST /groups/{id}/active` | Отношения, сильнейшие связи, соперничество, группы; роспуск/возврат группы |
| `GET /guilds`, `POST /guilds/{id}/election`, `PUT /guilds/{id}/traditions`, `POST /guilds/found-now` | Гильдии: репутация, традиции, отношения, история; выборы сейчас (только ИИ-гильдии); основать ИИ-гильдию |
| `GET/POST /outreach/exceptions` | Исключения: игроки (по UR-номеру), ИИ без права писать первыми |
| `GET /players/{uralia_id}` | Всё об игроке со стороны ИИ: приватность, лимиты, отношения, круг, личные сообщения с ИИ |
| `POST /admin/api/web/chat` | Теперь и в `news`, `region:*`, `event:*` |

## Планируемое Admin API AI Control Center (`/admin/api/ai/*`)
Будет детализироваться по мере этапов; все изменяющие маршруты — с ролями (D-08), валидацией, журналом и откатом.
| Группа | Примеры |
|---|---|
| Population | `GET /population`, `POST /population/spawn` (массовое создание), `POST /population/mode` |
| Characters | `GET /characters?query=`, `GET/PATCH /characters/{id}`, `POST /characters/{id}/run` (ручной запуск) |
| Personality / Behavior | `GET/PUT /archetypes`, `GET/PUT /behavior/templates`, `POST /simulate` |
| Social | `GET /relationships?id=`, `GET /graph`, `GET /groups` |
| Memory | `GET /characters/{id}/memory`, `POST …/checkpoint`, `POST …/restore`, `GET /memory/search` |
| Scheduler | `GET/PUT /schedules`, `GET /tasks?status=`, `POST /tasks/{id}/retry` |
| Chat | `GET/PUT /chat/settings` (частота, длина, каналы) |
| Economy & PvP | `GET/PUT /economy/limits`, `GET/PUT /pvp/settings` |
| Events | `GET/PUT /events/settings` |
| Infrastructure | `GET /director/status`, `POST /director/flags`, `GET /metrics`, `GET /audit` |
