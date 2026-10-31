# URALIA - Database & API Blueprint

## Таблицы
users, player_profiles, sessions, heroes, factions, classes, player_heroes, formations, campaign_regions, campaign_nodes, player_campaign_progress, battles, wallets, wallet_transactions, summon_pools, summon_history, afk_claims, fortress_buildings, quests, player_quests, mail_messages, player_mail, guilds, guild_members, guild_contributions, ai_personas, ai_activity_log, ai_memory, content_packages, content_manifest_versions, content_installations, audit_events, admin_actions.

## Правила
PostgreSQL - источник истины. Валюты меняются транзакционно и отражаются в неизменяемом wallet ledger. Для наград и claims обязательны idempotency keys. AFK вычисляется по серверному времени. Доступ к объектам проверяется на сервере. Важные действия аудируются.

## API baseline
POST /api/v1/auth/guest
POST /api/v1/auth/link
POST /api/v1/auth/refresh
GET /api/v1/player/me
GET /api/v1/player/bootstrap
GET /api/v1/heroes
GET /api/v1/player/heroes
POST /api/v1/formation
POST /api/v1/battles/validate
POST /api/v1/campaign/{node_id}/complete
POST /api/v1/summon
POST /api/v1/rewards/afk/claim
GET /api/v1/fortress
POST /api/v1/fortress/buildings/{code}/upgrade
GET /api/v1/quests
POST /api/v1/quests/{id}/claim
GET /api/v1/mail
POST /api/v1/mail/{id}/claim
GET /api/v1/content/manifest
POST /api/v1/content/verify-install
GET /health/live
GET /health/ready

Все изменяющие запросы авторизуются, валидируются, ограничиваются по частоте и защищаются от повторного выполнения.
