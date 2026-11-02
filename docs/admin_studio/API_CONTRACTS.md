# Контракты API [Предложение]

## 1. Общие правила

- Базовый путь Studio: `/studio/api/v1` (новый; существующие `/admin/api/*` работают параллельно до переноса).
- Клиентские (игровые) добавления: `/api/v1/client/config-status`, `/api/v1/client/preview-bundle` (игровой префикс).
- Схемы — pydantic-модели → OpenAPI 3.1 (FastAPI генерирует) → типы TypeScript для Studio (`openapi-typescript`).
- Версионирование: мажорная версия в пути (`v1`); внутри версии только обратно совместимые добавления полей.
  Удаление/изменение смысла поля → `v2`, `v1` живёт минимум 2 выпуска Studio.
- Авторизация: `Authorization: Bearer <access JWT aud=studio>`; права проверяются зависимостью `require("perm")`.
- Мутации: `Idempotency-Key` (обязателен для publish/activate/rollback/assets), `If-Match` для черновиков.
- Пагинация: `?limit=&cursor=`; ответ `{items, next_cursor}`.

## 2. Формат ошибок (совместим с текущим [Код: `core/errors.py` → `{"detail": {"code", "message"}}`])

```json
{"detail": {"code": "validation_failed", "message": "Конфигурация не прошла проверку",
            "errors": [{"path": "/changes/2/fields/rarity", "rule": "range", "message": "rarity: 1…6", "value": 99}],
            "request_id": "01J…"}}
```
| HTTP | code (примеры) |
|---|---|
| 400 | bad_request, bad_patch |
| 401 | unauthenticated, session_expired |
| 403 | forbidden, step_up_required |
| 404 | not_found |
| 409 | version_conflict (с `current_etag`), already_published, environment_locked |
| 410 | preview_expired |
| 413 | too_large |
| 422 | validation_failed |
| 429 | rate_limited (`Retry-After`) |

## 3. Каталог эндпоинтов

| Группа | Метод и путь | Право | Назначение |
|---|---|---|---|
| Auth | POST `/auth/login` | — | логин+пароль(+TOTP) → access, refresh |
| | POST `/auth/refresh`, POST `/auth/logout` | сессия | ротация, отзыв |
| | POST `/auth/step-up` | сессия | подтверждение для опасных операций (5 мин) |
| | GET `/me` | сессия | профиль, права |
| Users | GET/POST/PATCH `/admin-users`, PUT `/admin-users/{id}/roles` | users:manage | учётки и роли |
| Registry | GET `/modules`, GET `/configs?module=` | read | список |
| | GET `/configs/{id}` | read | определение, схема, активные версии по окружениям |
| | GET `/configs/{id}/versions`, GET `/configs/{id}/versions/{v}` | read | история |
| | GET `/diff?config=&a=&b=` | read | структурный diff |
| Drafts | POST `/drafts` {config_id, base_version, branch} | <module>:edit | новый черновик |
| | GET/PUT/PATCH `/drafts/{id}` (If-Match) | <module>:edit | полное / JSON Patch |
| | DELETE `/drafts/{id}` | <module>:edit | удалить черновик |
| Changesets | POST `/changesets` {draft_ids, title} | edit | собрать набор |
| | POST `/changesets/{id}/validate` | edit | → ValidationReport |
| | POST `/changesets/{id}/submit` | edit | → APPROVAL |
| | POST `/changesets/{id}/approve` {environment, comment} | approve (+step-up для prod) | → PUBLISHED |
| | POST `/changesets/{id}/reject` {comment} | approve | → REJECTED |
| Patches | POST `/patches/import` (zip/json) | edit | ZIP-патч → changeset (DRAFT) с отчётом |
| | GET `/patches/task?config=&id=` , GET `/patches/template` | read | задание и шаблон для ИИ (как v1 [Код]) |
| Publishing | GET `/publications`, GET `/publications/{id}` | read | |
| | POST `/environments/{env}/activate` {publication_id} | activate:<env> | → ACTIVE |
| | POST `/environments/{env}/rollback` {to_publication_id?} | rollback:<env> | → ROLLED_BACK |
| | GET `/environments` | read | активные версии, статусы |
| Preview | POST `/preview-sessions` {draft_ids, flags} | edit | токен, URL |
| | DELETE `/preview-sessions/{id}` | edit | отзыв |
| Assets | POST `/assets` (multipart), GET `/assets?q=&tag=&kind=` | assets:edit / read | медиатека |
| | GET `/assets/{id}`, POST `/assets/{id}/versions`, GET `/assets/unused` | … | |
| Audit | GET `/audit?actor=&object=&from=` | audit:read | журнал |
| Monitoring | GET `/monitoring/overview`, `/monitoring/applied?env=`, `/monitoring/jobs` | monitoring:read | состояние |
| Game client | GET `/api/v1/client/preview-bundle?token=` | токен preview | черновой бандл |
| | POST `/api/v1/content/verify-install` (существует, + поля) | игрок | Applied |

## 4. Примеры

**Создать черновик и изменить поле (телефон, частичное обновление)**
```http
PATCH /studio/api/v1/drafts/8f1c
If-Match: "sha256:4a7e…"
Content-Type: application/json-patch+json

[{"op": "replace", "path": "/gold", "value": 2500}]
```
```json
{"id": "8f1c", "config_id": "economy.starting_wallet", "base_version": 3, "etag": "sha256:91b0…",
 "document": {"gold": 2500, "crystals": 200, "summon_essence": 1}, "updated_at": "2026-11-02T10:00:00Z"}
```

**Утвердить и опубликовать в PRODUCTION**
```http
POST /studio/api/v1/changesets/42/approve
Idempotency-Key: 6f2d…
Authorization: Bearer …   (step-up < 5 мин)

{"environment": "production", "comment": "Акция выходного дня"}
```
```json
{"changeset_id": 42, "status": "PUBLISHED", "publication": {"id": 17, "sha256": "…",
 "versions": [{"config_id": "economy.starting_wallet", "version": 4}], "client_package": null}}
```

**Активировать**
```json
POST /studio/api/v1/environments/production/activate  {"publication_id": 17}
→ {"environment": "production", "active": [{"config_id": "economy.starting_wallet", "version": 4}],
   "status": "ACTIVE", "applied": {"server": "ok", "clients": {"ok": 0, "failed": 0, "pending": 128}}}
```
