# URALIA ADMIN STUDIO — фаза 01: архитектура и технический план

Статус: **документация на рассмотрение владельца**. Код, БД, API, сцены и скрипты на этой фазе не менялись.

Пометки достоверности во всех документах:
- **[Код]** — проверено в репозитории (путь указан);
- **[Док]** — взято из существующей документации проекта;
- **[Предложение]** — архитектурное решение этой фазы, ещё не реализовано.

| № | Документ | О чём |
|---|---|---|
| 0 | [AUDIT_CURRENT_STATE.md](AUDIT_CURRENT_STATE.md) | Аудит: что реально есть в проекте (таблица систем) |
| 1 | [ADMIN_STUDIO_ARCHITECTURE.md](ADMIN_STUDIO_ARCHITECTURE.md) | Общая архитектура, диаграммы, главные решения |
| 2 | [SYSTEM_COMPONENTS.md](SYSTEM_COMPONENTS.md) | 15 компонентов: назначение, входы/выходы, ошибки |
| 3 | [TECHNOLOGY_SELECTION.md](TECHNOLOGY_SELECTION.md) | Compose / Flutter / React+Capacitor / Godot — сравнение |
| 4 | [GAME_CONTROL_MATRIX.md](GAME_CONTROL_MATRIX.md) | Каталог управляемых систем, категории A–D |
| 5 | [CONFIGURATION_SYSTEM.md](CONFIGURATION_SYSTEM.md) | Configuration Registry, схемы, версии |
| 6 | [UI_EDITOR_ARCHITECTURE.md](UI_EDITOR_ARCHITECTURE.md) | Hybrid-редактор (Simple / Pro), компоненты, связь с Godot |
| 7 | [PREVIEW_SYSTEM.md](PREVIEW_SYSTEM.md) | Static / Interactive / Game Runtime Preview |
| 8 | [ASSET_MANAGEMENT.md](ASSET_MANAGEMENT.md) | Медиатека |
| 9 | [DRAFT_PUBLISHING_WORKFLOW.md](DRAFT_PUBLISHING_WORKFLOW.md) | DRAFT → … → ACTIVE, ошибки, повторы |
| 10 | [VERSION_MANAGEMENT.md](VERSION_MANAGEMENT.md) | История, сравнение, откат, конфликты |
| 11 | [GODOT_INTEGRATION.md](GODOT_INTEGRATION.md) | Что меняется в клиенте |
| 12 | [SECURITY_MODEL.md](SECURITY_MODEL.md) | Авторизация, роли, опасные операции |
| 13 | [DATABASE_DESIGN.md](DATABASE_DESIGN.md) | ER-диаграмма, новые таблицы |
| 14 | [API_CONTRACTS.md](API_CONTRACTS.md) | Каталог эндпоинтов, схемы, ошибки |
| 15 | [ENVIRONMENTS_AND_RELEASES.md](ENVIRONMENTS_AND_RELEASES.md) | DEV / STAGING / PROD |
| 16 | [PERFORMANCE_AND_SCALABILITY.md](PERFORMANCE_AND_SCALABILITY.md) | Нагрузка, кэш, мобильный холст |
| 17 | [IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md) | Последовательность и оценка сложности |
| 18 | [OPEN_QUESTIONS_AND_DECISIONS.md](OPEN_QUESTIONS_AND_DECISIONS.md) | Решения на согласование |
| — | [REPORT.md](REPORT.md) | Итоговый отчёт фазы (17 пунктов) |

Диаграммы — Mermaid (рендерятся на GitHub).
