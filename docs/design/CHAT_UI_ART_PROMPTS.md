# Арт для экрана чата — промпты

Экран чата уже работает с процедурным оформлением (рамки, золото, бирюза). Когда в папке
`client/assets/ui/chat/` появляются картинки с именами из таблицы, игра автоматически использует их вместо
процедурных элементов. Нужен PNG с прозрачным фоном (кроме фона и баннеров).

Общий стиль для всех промптов (добавлять в конец каждого):
> dark fantasy mobile game UI, Ural mountains and Bashkir ornament motifs, deep graphite and dark teal, polished gold trim,
> subtle turquoise gems, premium, clean edges, high detail, no text, no letters, no watermark, transparent background

| Файл | Размер | Как используется | Промпт (к нему добавить общий стиль) |
|---|---|---|---|
| `panel.png` | 1024×1536 | Рамка всего окна, 9-slice, поля по 40 px | ornate rectangular window frame for a mobile game, thick gold border with Bashkir ornament, small turquoise diamonds in corners, a crest at the top center, dark teal empty center |
| `title_plaque.png` | 880×200 | Табличка под словом «Чат», 9-slice 40 px | horizontal title plaque, dark teal glass center, gold ornamental frame with pointed diamond ends left and right, small turquoise gem accents |
| `tab.png` | 600×200 | Вкладка (неактивная), 9-slice 30 px | game tab button, dark teal background, thin gold frame with angled corners, subtle inner glow |
| `tab_active.png` | 600×200 | Активная вкладка, 9-slice 30 px | game tab button selected state, warm golden glow, bright gold frame with angled corners, amber inner light |
| `bubble.png` | 512×256 | «Пузырь» сообщения, 9-slice 28 px | chat speech bubble for a fantasy game, dark translucent teal glass, thin turquoise and gold border, small tail on the top left |
| `bubble_mine.png` | 512×256 | Ваше сообщение, 9-slice 28 px | chat speech bubble, dark amber glass, thin gold border, small tail on the top left |
| `avatar_ring.png` | 256×256 | Кольцо поверх круглого аватара | circular avatar frame, gold ring with Bashkir ornament, turquoise gem at the bottom, empty transparent center |
| `background.png` | 1024×1536 | Фон ленты сообщений (полупрозрачно) | night Ural mountains landscape, dark moody teal sky, misty valleys, very dark, low contrast (с фоном, без прозрачности) |
| `event_raids.png` | 1024×256 | Фон карточки события «рейд/босс» | wide banner, giant stone golem guardian with glowing turquoise runes on the right side, dark teal background fading to the left (с фоном) |
| `event_tournaments.png` | 1024×256 | Фон карточки «турнир» | wide banner, crossed golden sabers and a trophy on the right, dark teal background fading to the left (с фоном) |
| `event_events.png` | 1024×256 | Фон карточки «событие мира» | wide banner, dark army silhouettes under Toratau mountain with purple fog on the right, fading to the left (с фоном) |
| `event_guild.png` | 1024×256 | Фон карточки «гильдия» | wide banner, golden guild banner with eagle emblem on the right, fading to the left (с фоном) |

## Как передать
Сгенерируйте картинки и пришлите их в чат с именами файлов из таблицы. Я положу их в `client/assets/ui/chat/`,
проверю на скриншотах и соберу APK. Можно присылать по частям — недостающие элементы останутся процедурными.

## Что не делаем на этом этапе
Картинки и стикеры в сообщениях игроков (как в макете) — это вложения, они были исключены из задачи по чату
(нужны хранилище файлов и модерация изображений). Эмодзи доступны через кнопку 😊.
