# Сборка

Godot 4.5.1 + шаблоны экспорта 4.5.1 (Android, Web).

## Android (APK, arm64)
```bash
cd client
godot --headless --path . --import
godot --headless --path . --export-release "Android" ../build/uralia-release.apk   # или --export-debug
```
Версия — `Config.CLIENT_VERSION` и `export_presets.cfg` (`version/name`, `version/code`). Разрешения: INTERNET,
ACCESS_NETWORK_STATE, VIBRATE (вибрация отключаема в настройках). Секретов сервера в APK нет.

Публикация: файл `uralia-latest.apk` в ветке `apk` репозитория
(`https://github.com/maillunex-lang/UfaArena/raw/apk/uralia-latest.apk`) и/или загрузка через `/admin` → «Выпуски».

## Web
```bash
cd client
godot --headless --path . --export-release "Web" ../build/web/index.html
```
Пресет «Web»: без потоков (не нужны заголовки COOP/COEP), рендер `gl_compatibility` только для web
(`rendering/renderer/rendering_method.web`), Android остаётся на Mobile.

Развёртывание на сервере: скопировать содержимое `build/web/` в `/opt/uralia/web/` (том `./web:/srv/var/web:ro`)
и перезапустить `api` (`docker compose up -d`). Игра откроется по адресу `http://<сервер>:8000/play/`.

## Проверки перед выпуском
```bash
cd server && .venv/bin/python -m pytest -q            # SQLite
URALIA_DATABASE_URL=postgresql+psycopg://... .venv/bin/python -m pytest -q   # PostgreSQL
cd ../client && godot --headless --path . res://tools/Check.tscn               # компиляция скриптов
URALIA_E2E=out URALIA_SERVER_URL=http://127.0.0.1:8000 godot --path .          # сквозной сценарий
URALIA_E2E_UI=out URALIA_SERVER_URL=http://127.0.0.1:8000 godot --path .       # визуальный обход
```
