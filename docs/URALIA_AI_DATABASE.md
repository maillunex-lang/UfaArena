# URALIA Living World AI — СТРУКТУРА БД

> PostgreSQL 16 (прод), SQLite (тесты). Миграции Alembic, сейчас голова — `0011`. Принцип ТЗ §6: использовать
> существующие таблицы, если они уже выполняют функцию; новые — только для того, чего нет.

## Существующие таблицы, связанные с ИИ
| Таблица | Назначение |
|---|---|
| `users` (`kind='ai'`) | Аккаунт ИИ — тот же, что у игроков |
| `player_profiles` (`is_ai`, `ai_prefs`) | Профиль, уровень, VIP, сила, присутствие; `ai_prefs` — настройки игрока по отношению к ИИ |
| `ai_personas` | Архетип, темперамент, стиль, расписание, интересы, предыстория, `next_action_at`, дневной счётчик |
| `ai_activity_log` | Журнал действий ИИ (**сейчас чистится через 7 дней** — изменить, D-06) |
| `ai_memory` | Факты памяти: о ком, текст, вес, срок |
| `guilds` (`is_ai`, `ai_policy`) | ИИ-гильдии; политика гильдии к ИИ |
| `server_settings` (`ai_switches`) | Глобальные переключатели ИИ |
| `admin_actions` | Журнал действий администраторов |
| Игровые таблицы | `player_heroes`, `formations`, `wallets`, `wallet_transactions`, `player_campaign_progress`, `arena_*`, `guild_*`, `chat_messages`, `friendships`, `world_event_contributions`, `stat_counters` — общие для ИИ и игроков |

## Добавлено в фазе 2 (миграция 0011)
| Таблица / поле | Назначение |
|---|---|
| `ai_tasks` | Очередь Director: `key` (уникальный, идемпотентность), `kind`, `persona_id`, `priority`, `payload`, `status` (pending/running/done/failed/simulated/cancelled), `run_after`, `attempts`, `max_attempts`, `lease_until`, `result`, `error`, `created_at`, `finished_at` |
| `ai_task_history` | Завершённые задачи после сжатия очереди |
| `ai_events` | События игры для ИИ (`dm`, `mention`, …): `persona_user_id`, `payload`, `due_at`, `handled_at` |
| `ai_schedule_profiles` | Групповые расписания: часы, пиковые часы, сдвиг пояса, длительность сессии, дни отдыха, вес |
| `ai_personas.schedule_profile`, `ai_personas.session_until` | Профиль расписания персонажа и конец текущей игровой сессии |
| `server_settings`: `ai_director`, `ai_director_history`, `ai_director_status` | Настройки и режим, история для отката, сердцебиение и метрики |

## Сопоставление сущностей ТЗ §6 (план)
| Сущность ТЗ | Решение |
|---|---|
| ai_profiles | **есть**: `users` + `player_profiles` + `ai_personas` |
| ai_personalities, ai_traits | расширить `ai_personas`: `traits`, `ambitions`, `habits`, `personality_version` (JSON) |
| ai_archetypes | **новая** `ai_archetypes` (редактируются в админке; сейчас — константы в коде) |
| ai_progress, ai_heroes, ai_inventory | **есть**: игровые таблицы (тот же прогресс, что у игроков; дублирование запрещено) |
| ai_relationships | **новая**: `(subject_id, object_id)` → симпатия, доверие, соперничество, неприязнь, история; ИИ↔ИИ и ИИ↔игрок |
| ai_social_groups | **новая** `ai_social_groups` + участники |
| ai_memories | **есть** `ai_memory` → добавить `kind`, `importance`, `version` |
| ai_memories_archive, ai_biographies | **новые**: сжатые итоги и биография (не удаляются) |
| ai_guild_memberships | **есть** `guild_members` |
| ai_schedules | ✅ `ai_personas.schedule` + `ai_schedule_profiles` (0011) |
| ai_behavior_rules, ai_behavior_templates | **новые** (правила и шаблоны поведения как данные) |
| ai_goals | **новая** (долгосрочные цели ИИ) |
| ai_tasks, ai_task_history | ✅ **созданы в 0011** |
| ai_dialogues, ai_messages, ai_channels | **есть** `chat_messages`; контекст бесед — в памяти; каналы — настройки чата |
| ai_economy, ai_transactions | **есть** `wallets`, `wallet_transactions` (тот же журнал) |
| ai_pvp_history | **есть** `arena_matches`, `tournament_matches`, `guild_war_attacks` |
| ai_event_participation | **есть** `world_event_contributions` (+ флаг вклада ИИ, D-05) |
| ai_statistics | **есть** `stat_counters` + агрегаты `ai_activity_log` |
| ai_settings | `server_settings` (ключи `ai_*`) |
| ai_admin_logs | **есть** `admin_actions` |

Все новые миграции — аддитивные, с `downgrade`, проверяются `alembic check` и откатом на PostgreSQL.
