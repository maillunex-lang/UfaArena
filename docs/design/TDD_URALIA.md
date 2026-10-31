# URALIA - Technical Design Document

## Архитектура
Godot 4 Android client; Python + FastAPI backend; PostgreSQL durable store; Redis cache/locks/rate limits; object storage/CDN for content. Начать с модульного монолита, выделять сервисы по необходимости. Ручная сборка APK утверждена.

## Клиентские модули
bootstrap, navigation, Liquid Glass UI, auth, profile, heroes, formation, battle runtime, campaign, fortress, summon, progression, economy view, content loader, update manager, local cache, telemetry, settings.

## Серверные модули
auth, profiles, heroes, formations, battle validation, campaign, summon, progression, economy ledger, AFK rewards, fortress, quests, mail, guilds, social, PvP, bosses, events, shops, payments, content registry, update service, population AI, admin, audit, telemetry.

## Базовые таблицы
users, player_profiles, sessions, heroes, factions, classes, player_heroes, formations, campaign_regions, campaign_nodes, player_campaign_progress, battles, wallets, wallet_transactions, summon_pools, summon_history, afk_claims, fortress_buildings, quests, player_quests, mail_messages, player_mail, guilds, guild_members, guild_contributions, ai_personas, ai_activity_log, ai_memory, content_packages, content_manifest_versions, content_installations, audit_events, admin_actions.

## API
POST /api/v1/auth/guest, /auth/link, /auth/refresh; GET /player/me, /player/bootstrap, /heroes, /player/heroes; POST /formation, /battles/validate, /campaign/{node_id}/complete, /summon, /rewards/afk/claim; GET /fortress; POST /fortress/buildings/{code}/upgrade; GET /quests; POST /quests/{id}/claim; GET /mail; POST /mail/{id}/claim; GET /content/manifest; POST /content/verify-install; GET /health/live, /health/ready.

## Безопасность
Сервер - источник истины для валют, прогресса, призывов, AFK и наград. TLS, короткоживущие access tokens, hashed/rotated refresh tokens, rate limiting, валидация, защита replay, idempotency, audit log. Секретов backend в APK нет. Платёжные callback проверяются сервером.

## Battle flow
Сервер проверяет узел и отряд, выдаёт battle_id/seed/config. Клиент визуализирует бой. Результат проверяется сервером, награды выдаются транзакционно. Для PvP нужна серверная симуляция или строгий проверяемый протокол.

## Update System
Подписанный manifest, SHA-256, версии, зависимости, minimum client version, каналы dev/test/beta/stable, resume download, атомарная активация, rollback, kill switch. Контентные пакеты не исполняют произвольный код.

## AI Population Engine
Отдельный модуль: population manager, persona registry, scheduler, dialogue, memory, activity simulator, guild AI, matchmaking adapter, safety filter, audit. Не запускать LLM на каждого агента. Предусмотреть deterministic fallback и бюджетные лимиты. Не запускать тяжёлый inference на слабом VPS. AI раскрывается в профиле; не подделывать число реальных игроков и рейтинги.

## Тестирование
Unit, integration, contract, security, load, Android smoke, device matrix, FPS/memory/thermal, offline/reconnect, package signature/hash/rollback, idempotency, wallet reconciliation, backup restore.
