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
