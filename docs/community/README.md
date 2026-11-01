# URALIA Living Community — этап 01: архитектура разговорных сцен

Проектная документация (код и БД на этом этапе не меняются). Порядок чтения:

| № | Документ | Пункт ТЗ |
|---|---|---|
| 00 | [00_ANALYSIS.md](00_ANALYSIS.md) — анализ существующей системы и точки интеграции | §15 |
| 01 | [01_ARCHITECTURE.md](01_ARCHITECTURE.md) — Dialogue Scene Architecture | 16.1 |
| 02 | [02_SCENE_TAXONOMY.md](02_SCENE_TAXONOMY.md) — каталог сцен | 16.2, §4 |
| 03 | [03_STATE_MACHINE.md](03_STATE_MACHINE.md) — конечный автомат сцены | 16.3, §9 |
| 04 | [04_DATA_MODEL.md](04_DATA_MODEL.md) — модель данных контекста сцены | 16.4 |
| 05 | [05_TRIGGERS_AND_PARTICIPANTS.md](05_TRIGGERS_AND_PARTICIPANTS.md) — триггеры и выбор участников | 16.5, 16.6, §10 |
| 06 | [06_GROUP_CONVERSATION.md](06_GROUP_CONVERSATION.md) — групповые беседы | 16.7, §6, §11 |
| 07 | [07_OFFTOPIC_ENGINE.md](07_OFFTOPIC_ENGINE.md) — свободные темы | 16.8, §5 |
| 08 | [08_HUMOR_PROFANITY.md](08_HUMOR_PROFANITY.md) — юмор, подколы, завуалированный мат, взрослый юмор | 16.9, §7, §4E |
| 09 | [09_INTERESTS.md](09_INTERESTS.md) — модель интересов | 16.10, §8 |
| 10 | [10_MEMORY_RELATIONSHIPS.md](10_MEMORY_RELATIONSHIPS.md) — память и отношения | 16.11, 16.12, §12 |
| 11 | [11_PERFORMANCE.md](11_PERFORMANCE.md) — производительность и масштаб | 16.13, §14 |
| 12 | [12_EDGE_CASES.md](12_EDGE_CASES.md) — пограничные случаи и защита от искусственности | 16.14, §13 |
| 13 | [13_TEST_SCENARIOS.md](13_TEST_SCENARIOS.md) — тестовые сценарии | 16.15 |
| 14 | [14_ROADMAP.md](14_ROADMAP.md) — план реализации | 16.16 |
| 15 | [15_DECISIONS.md](15_DECISIONS.md) — **решения, требующие согласования** | §17 |

Связь с Living World AI: это развитие уже работающих модулей (`app/ai/*`, `app/social/ai/*`), без параллельных систем
памяти и отношений. Утверждённые параметры этапа: Communication Level MAXIMUM, Frequency BALANCED, Memory DEEP,
Autonomy FULL, Social ADAPTIVE, Dialogue Depth MAXIMUM, Speech Realism MAXIMUM, Scope FULL, Natural Conversational,
Slang / Censored Profanity / Adult Humor / Off-topic — ENABLED (с ограничениями из [15_DECISIONS.md](15_DECISIONS.md)).
