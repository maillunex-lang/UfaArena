# 04. Модель данных контекста сцены

Новые таблицы (аддитивная миграция, план совместимости — в [14_ROADMAP.md](14_ROADMAP.md)). Существующие
`ai_memory`, `ai_relationships`, `ai_personas`, `chat_messages`, `server_settings` переиспользуются.

## `ai_scenes`
| Поле | Тип | Назначение |
|---|---|---|
| id | uuid | |
| channel | str(80) | `global`, `guild:…`, `region:…`, `event:…`, `group:…`, `dm:ai:ai` |
| category / kind | str | A…G / тип сцены из каталога |
| topic | json | `{code, title, source: interest|memory|event|game|player, seed}` |
| tone | str | serious, light, joking, tense, flirty18, warm |
| state | str | состояние автомата |
| initiator_id | uuid | пользователь-ИИ |
| plan | json | дуга сцены: целевая длина, ожидаемые переходы, «зацепки» |
| mood | json | эмоциональный фон: `{valence, arousal, tension}` |
| audience | json | `{real_readers: n, adult_ok: bool}` на момент старта |
| turns_done / max_turns | int | |
| next_turn_at | ts | когда следующий шаг (для восстановления) |
| started_at / ended_at | ts | |
| outcome | json | итог: смех, спор не решён, примирение, обещание… |
| llm_used | int | сколько запросов к модели ушло на сцену |

## `ai_scene_participants`
`scene_id`, `user_id`, `role` (initiator, core, joiner, observer, real_player), `stance` (за/против/нейтрально по теме),
`engagement` 0…1 (падает с каждым ходом, растёт от интересной темы и обращений), `turns`, `last_turn_at`, `left_at`.

## `ai_scene_turns` (краткосрочная память сцены, хранится 7 дней, затем — только итог)
`scene_id`, `seq`, `speaker_id`, `move`, `addressee_id`, `reply_to_seq`, `text`, `source` (llm/grammar/script),
`message_id` (ChatMessage), `created_at`.

## Расширения существующих сущностей (JSON-поля, без новых колонок где возможно)
- `ai_personas.voice` += `{slang: 0…1, profanity: 0…1, rudeness_with_friends: 0…1, adult_humor: 0…1, humor_style: [...]}`
- `ai_personas.counters` += `{social_battery: 0…1, last_scene_at}` (усталость от общения)
- **Новое** `ai_personas.interests_ext` (json) — профиль интересов (см. [09_INTERESTS.md](09_INTERESTS.md));
  старое поле `interests` (игровые) остаётся как есть.
- `ai_relationships.history` += события `scene_*`; **новое** `ai_relationships.inside_jokes` (json, до 10 шуток).
- `ai_memory.kind` += `topic_open` (незавершённая тема), `inside_joke`, `personal_story`, `preference`.
- Игроки: **новое** поле настроек `player_profiles.ai_prefs.adult_content` (по умолчанию `false`) и подтверждение
  возраста (D-C1).

## Контекст сцены в рантайме (`SceneContext`, не хранится целиком)
канал и его последние 20 сообщений; читатели (живые игроки онлайн, их настройки 18+/скрытия ИИ); время суток по МСК;
активные события мира; участники с профилями (черты, голос, настроение, интересы, социальная батарейка); попарные
отношения и внутренние шутки; память о теме (что говорили раньше, незавершённое); история сцены (последние 10 ходов).
