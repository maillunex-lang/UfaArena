# URALIA Living World AI — СТРУКТУРА БД

> PostgreSQL 16 (прод), SQLite (тесты). Миграции Alembic, сейчас голова — `0014`. Принцип ТЗ §6: использовать
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

## Добавлено в фазе 3 (миграция 0012)
| Таблица / поле | Назначение |
|---|---|
| `ai_personas`: `traits`, `ambitions`, `habits`, `voice`, `counters`, `mood`, `tier`, `pace`, `personality_version` | Черты 0…1, амбиции, привычки, манера речи, счётчики (серии, победы, тактика, дрейф черт), настроение −1…1, слой силы, темп, версия характера |
| `ai_memory`: `kind`, `importance`, `created_at` | Вид воспоминания, важность 0…5, время (срок хранения считается от него; больше не удаляется по `expires_at`) |
| `ai_archetypes` | Архетипы как данные: название, описание, интересы, стили, сдвиг черт, амбиции, вес, включён |
| `ai_persona_snapshots` | Версии/контрольные точки характера (причина, кто, когда, данные) |
| `ai_memory_archive` | Помесячный архив на персонажа: счётчики действий и видов памяти + важные воспоминания текстом (уникально persona+период) |
| `ai_biographies` | Биография: главы `{at, kind, text}` |
| `server_settings`: `ai_speech`, `ai_memory_settings`, `ai_tiers` (+ `_history`) | Настройки речи, памяти, слоёв с историей для отката |

## Добавлено в фазе 4 (миграция 0013)
| Таблица | Назначение |
|---|---|
| `ai_relationships` | Отношение ИИ (subject) к ИИ или игроку (object): симпатия −1…1, доверие, соперничество, неприязнь 0…1, встречи, история (последние 20), уникально по паре |
| `ai_social_groups`, `ai_social_group_members` | Неформальные группы (название, вид, тема, основатель, активна) и участники (ИИ и игроки) |
| `ai_guild_state` | ИИ-сторона гильдии: репутация, традиции, отношения с другими гильдиями, история (выборы, союзы, войны), дата выборов |
| `ai_player_watch` | Что ИИ заметили об игроке: уровень, когда видели, когда писали, счётчики в день/неделю, разовые флаги |
| `guild_alliances`, `guild_alliance_members`, `guild_alliance_proposals` | Союзы гильдий (до 3), участники, предложения |
| `server_settings`: `ai_channels`, `ai_guilds`, `ai_outreach`, `ai_outreach_exceptions`, `ai_chat_pause` | Настройки каналов, гильдий ИИ, общения; исключения; паузы чата |

## Добавлено в фазе 5 (миграция 0014)
| Поле / ключ | Назначение |
|---|---|
| `world_events.ai_progress` | Вклад ИИ-жителей отдельной строкой (≤ 20% цели), учитывается в итоге события |
| `ai_personas.counters`: `strategy`, `economy`, `daily{battles,summons,upgrades,arena}`, `camp_losses_row`, `camp_cleared`, `rebuilds` | Тактика, экономическая стратегия, дневные лимиты, серии в кампании |
| `server_settings`: `ai_play`, `ai_pvp`, `ai_events` | Настройки развития по правилам, PvP, событий (с историей и откатом) |
| `idempotency_keys` (ключи `ai…`) | Ключи повтора игровых заходов ИИ; старше 2 суток удаляются Director |

## Сопоставление сущностей ТЗ §6 (план)
| Сущность ТЗ | Решение |
|---|---|
| ai_profiles | **есть**: `users` + `player_profiles` + `ai_personas` |
| ai_personalities, ai_traits | ✅ поля `ai_personas` (0012) |
| ai_archetypes | ✅ `ai_archetypes` (0012) |
| ai_progress, ai_heroes, ai_inventory | **есть**: игровые таблицы (тот же прогресс, что у игроков; дублирование запрещено) |
| ai_relationships | ✅ `ai_relationships` (0013) |
| ai_social_groups | ✅ `ai_social_groups` + участники (0013) |
| ai_memories | ✅ `ai_memory` + `kind`, `importance`, `created_at` (0012); версии — через контрольные точки |
| ai_memories_archive, ai_biographies | ✅ `ai_memory_archive`, `ai_biographies` (0012) |
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
| ai_settings | ✅ `server_settings` (ключи `ai_*`) |
| ai_admin_logs | **есть** `admin_actions` |

Все новые миграции — аддитивные, с `downgrade`, проверяются `alembic check` и откатом на PostgreSQL.
