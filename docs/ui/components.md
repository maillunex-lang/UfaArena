# Компоненты

Все компоненты — статические функции `UI` (`client/src/ui/UI.gd`).

| Компонент | Сигнатура | Назначение |
|---|---|---|
| Кнопка | `button(text, kind="glass", min_w=0, h=96)` | kinds: `primary` (золото), `accent` (бирюза), `danger`, `dim`, `glass`; состояния normal/hover/pressed/disabled/focus, звук, вибрация |
| Загрузка кнопки | `set_loading(b, on)` | блокирует кнопку и показывает «…» на время запроса |
| Карточка | `card(border, pad)` | поверхность с рамкой |
| Секция | `section(text, action, cb)` | заголовок блока с ссылкой-действием («Все задания ›») |
| Вкладки | `tabs(items, current, cb, h)` | сегментированный переключатель |
| Прогресс | `progress(value, max, caption, color, h)` | полоса с подписью |
| Бейдж | `badge(n)` | счётчик на иконке |
| Тег редкости | `rarity_tag(rarity, text)` | цвет + (в режиме дальтонизма) число звёзд |
| Состояния | `state(kind, text, action, cb)` | `empty`, `error`, `offline`, `locked` с кнопкой действия |
| Скелетон | `skeleton(rows, h)` | заглушка на время загрузки |
| Подтверждение | `confirm(parent, title, body, ok_text, cb, danger)` | умное подтверждение важных действий |
| Плитка | `tile(icon, caption, sub, locked, badge_n)` | вход в раздел (Мир, Ещё, активности) |
| Переключатель | `toggle_row(text, on, cb)` | строка настройки со свитчем (крупная зона касания) |
| Панели | `glass_panel()`, `solid_panel()` | стекло / сплошная панель |
| Чип ресурса | `chip(...)` | ресурс в верхней панели |
| Награды | `rewards_row(rewards, size)` | иконки валют с количеством |
| Метка ИИ | `ai_badge()` | обязательная метка ИИ-персонажей |
| Время | `local_time(iso)` | локальное время события |

Оверлеи: `Notifications.gd` (центр уведомлений), `StoryDialog.gd` (сюжет, кнопка «Пропустить»),
`UpdateDialog.gd`, `PlayerPopup.gd`.
