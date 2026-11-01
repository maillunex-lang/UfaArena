"""Replaceable game art: catalog of slots (with advice and prompts), staging uploads and publishing them to
players as a content package (no new APK). The client looks up every slot at `art/<path>` in mounted
content and falls back to the built-in art when the slot is empty."""
from __future__ import annotations

import json
import struct
from pathlib import Path

from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.db import utcnow
from ..game import data as D

STYLE = ("dark fantasy mobile game art, Ural mountains and Bashkir ornament motifs, deep graphite and dark teal, "
         "polished gold accents, premium, high detail, no text, no watermark")
MAX_BYTES = 8 * 1024 * 1024
PACKAGE_ID = "ui.art"

CURRENCY_ICONS = {
    "gold": ("Золото", "a stack of ancient gold coins with a Bashkir sun ornament"),
    "crystals": ("Кристаллы", "a cluster of glowing turquoise crystals"),
    "summon_essence": ("Эссенция призыва", "a swirling violet-and-gold spirit orb in a small vessel"),
    "nature_essence": ("Эссенция природы", "a green glowing leaf drop with a kurai reed"),
    "ancient_seals": ("Древние печати", "a round bronze seal with ancient runes"),
    "guild_marks": ("Знаки гильдии", "a gold medallion with an eagle emblem"),
    "friend_tokens": ("Жетоны дружбы", "two clasped hands on a small silver token"),
    "raid_tickets": ("Билеты рейда", "a parchment ticket with a stone-golem seal"),
}
SECTION_ICONS = {
    "home": ("Главная (меню)", "a small fortress house with a golden roof"),
    "heroes": ("Герои (меню)", "a knight helmet with a turquoise plume"),
    "campaign": ("Поход (меню)", "a waving campaign flag on a spear"),
    "guild": ("Гильдия (меню)", "a heraldic shield with an eagle"),
    "world": ("Мир (меню)", "a round map of mountains and a river"),
    "more": ("Ещё (меню)", "four rounded tiles in a 2x2 grid, gold and teal"),
    "bell": ("Уведомления (колокольчик)", "a bell with a small turquoise gem"),
    "profile": ("Профиль", "a silhouette bust in a round medallion"),
    "fortress": ("Крепость", "a stone fortress tower"),
    "summon": ("Призыв", "a glowing summoning star portal"),
    "quests": ("Задания", "an unrolled quest scroll with a seal"),
    "mail": ("Почта", "a sealed envelope with a wax seal"),
    "settings": ("Настройки", "a bronze gear"),
    "afk": ("Дозор (AFK)", "a treasure chest with a lantern on top"),
    "events": ("События", "a bright gold four-pointed star"),
    "friends": ("Друзья", "two friendly figures side by side"),
    "chat": ("Чат", "a speech bubble with an ornament"),
    "crown": ("Корона / управление", "a golden crown with turquoise gems"),
    "ranks": ("Рейтинг", "a podium with three steps and a laurel"),
    "shop": ("Магазин", "a merchant sack with coins"),
    "arena": ("Арена", "two crossed sabers"),
    "lock": ("Закрыто", "a heavy bronze padlock"),
}
FACTION_ICONS = {
    "stone_sky": ("Каменное Небо", "a mountain peak with a sky spirit eye, grey-blue and silver"),
    "living_kurai": ("Живой Курай", "a kurai reed flute wrapped in leaves, green and gold"),
    "ashen_reach": ("Пепельный Предел", "a burning ember in an ash swirl, crimson and bronze"),
    "shulgan": ("Шульган", "a horned shadow skull with violet glow"),
}
BUTTONS = {
    "primary": ("Главная кнопка (золотая)", "polished warm gold", "«В бой», «Забрать», «Купить» — главные действия", "dark text sits on it: keep the middle light and even"),
    "accent": ("Акцентная кнопка (бирюзовая)", "deep teal with a bright turquoise rim", "активный выбор, «Перейти», «Открыть»", "light text sits on it: keep the middle dark and even"),
    "glass": ("Обычная кнопка (стекло)", "dark translucent teal glass with a thin gold rim", "вкладки, «Назад», второстепенные действия", "light text sits on it: keep the middle dark and even"),
    "danger": ("Опасное действие (красная)", "dark crimson with a copper rim", "«Выйти», «Исключить», удаление", "light text sits on it: keep the middle dark and even"),
    "dim": ("Неактивная кнопка", "muted graphite with a faint grey rim", "«В процессе», «Закрыто», недоступные действия", "light text sits on it: keep the middle dark and even"),
}
PANELS = {
    "glass": ("Стеклянная панель", "512×512", 64, "large dark translucent teal glass panel, thin gold border with small ornament in each corner", "основные окна экранов, нижняя навигация (если не загружен отдельный фон меню)"),
    "dialog": ("Окно диалога / подтверждения", "768×768", 80, "opaque dark graphite-teal dialog window, ornate gold border with Bashkir ornament corners and a small crest at the top centre", "подтверждения, уведомления, результат боя, контекстные окна"),
    "card": ("Карточка", "512×512", 48, "compact dark card plate, thin teal-gold border, subtle inner bevel", "все карточки: задания, события, гильдия, магазин, настройки"),
    "tile": ("Плитка раздела", "320×320", 48, "square menu tile, dark teal plate, gold border with a soft glow on the top edge", "плитки «Мир», «Ещё», активности на главной"),
}
REGION_LOOKS = {
    "r1_shikhany": "four lonely shikhan mountains above the Agidel river valley at dusk, Toratau in the distance",
    "r2_iremel": "snowy Iremel mountain slopes with stone rivers (kurums) and tundra",
    "r3_shulgantash": "the mouth of the Shulgan-Tash cave with ancient ochre wall paintings and an underground river",
    "r4_nugush": "the Nugush river valley with a reservoir, forested hills and morning mist",
    "r5_yangantau": "the burning mountain Yangantau with warm vapour rising from rock fissures",
    "r6_ufa_plateau": "the Ufa plateau with deep forests, karst canyons and a winding river",
    "r7_zilair": "the wide Zilair steppe plateau with feather grass and wild horses under a stormy sky",
}
RARITY_NAMES = {1: ("Обычная", "plain grey steel"), 2: ("Необычная", "green-tinted bronze"), 3: ("Редкая", "blue steel with sapphires"),
                4: ("Эпическая", "violet enamel with amethysts"), 5: ("Легендарная", "polished gold with turquoise gems and a soft glow"),
                6: ("Мифическая", "crimson and gold with flame ornaments and a strong glow")}

CHAT_UI = [
    ("panel.png", "Рамка окна чата", "1024×1536", "ornate rectangular window frame, thick gold border with Bashkir ornament, small turquoise diamonds in corners, crest at the top center, dark teal empty center, transparent background"),
    ("title_plaque.png", "Табличка заголовка", "880×200", "horizontal title plaque, dark teal glass center, gold ornamental frame with pointed diamond ends, transparent background"),
    ("tab.png", "Вкладка", "600×200", "game tab button, dark teal background, thin gold frame with angled corners, transparent background"),
    ("tab_active.png", "Активная вкладка", "600×200", "selected game tab button, warm golden glow, bright gold frame with angled corners, transparent background"),
    ("bubble.png", "Пузырь сообщения", "512×256", "chat speech bubble, dark translucent teal glass, thin turquoise and gold border, small tail top left, transparent background"),
    ("bubble_mine.png", "Ваше сообщение", "512×256", "chat speech bubble, dark amber glass, thin gold border, small tail top left, transparent background"),
    ("avatar_ring.png", "Кольцо аватара", "256×256", "circular avatar frame, gold ring with Bashkir ornament, turquoise gem at the bottom, empty transparent center"),
    ("background.png", "Фон ленты сообщений", "1024×1536", "night Ural mountains landscape, dark moody teal sky, misty valleys, very dark and low contrast"),
    ("event_raids.png", "Баннер события: рейд", "1024×256", "wide banner, giant stone golem with glowing turquoise runes on the right, dark teal background fading to the left"),
    ("event_tournaments.png", "Баннер события: турнир", "1024×256", "wide banner, crossed golden sabers and a trophy on the right, fading to the left"),
    ("event_events.png", "Баннер события мира", "1024×256", "wide banner, dark army under Toratau mountain in purple fog on the right, fading to the left"),
    ("event_guild.png", "Баннер события гильдии", "1024×256", "wide banner, golden guild banner with eagle emblem on the right, fading to the left"),
]


CLASS_EN = {"guardian": "shield-bearing guardian tank", "warrior": "warrior", "mage": "battle mage", "healer": "healer",
            "support": "healer and support", "ranger": "archer ranger", "summoner": "spirit summoner", "assassin": "assassin",
            "hybrid": "spellblade hybrid fighter"}
FACTION_EN = {"stone_sky": "Stone Sky faction (mountain stone and sky spirits, grey-blue, silver and gold palette)",
              "living_kurai": "Living Kurai faction (forest, reeds and kurai-flute nature magic, green and gold palette)",
              "ashen_reach": "Ashen Reach faction (ash, embers and steppe wind, crimson, black and bronze palette)",
              "shulgan": "Shulgan underworld (bone, shadow and violet glow, menacing)"}


def _ratio(size: str) -> tuple[int, int, str]:
    w, h = (int(x) for x in size.replace("x", "×").split("×"))
    from math import gcd
    g = gcd(w, h)
    return w, h, f"{w // g}:{h // g}"


def build_prompt(subject: str, size: str, composition: str, background: str, fmt: str = "PNG", lettering: bool = False) -> str:
    """Prompt with the exact output size first, so any image generator gets the format right."""
    w, h, ratio = _ratio(size)
    style = STYLE.replace(", no text,", ", lettering only as described above,") if lettering else STYLE
    return (f"{subject}.\n"
            f"Format: exactly {w}x{h} pixels, aspect ratio {ratio}, {fmt}.\n"
            f"Composition: {composition}.\n"
            f"Background: {background}.\n"
            f"Style: {style}.")


def _cap(t: str) -> str:
    return t[:1].upper() + t[1:]


TRANSPARENT = "fully transparent (alpha channel), no backdrop, no shadow plate"
NINE_SLICE = ("frame for a stretchable 9-slice UI element: all four corners and all edges complete, crisp and uniform, "
              "ornaments only in the corners and along the border, the middle area plain and calm so it can be stretched")


OPAQUE_NOTE = "Можно PNG или JPEG (прозрачность не нужна)."
ALPHA_NOTE = "Только PNG с прозрачным фоном (JPEG не поддерживает прозрачность)."


def _slot(path: str, title: str, size: str, where: str, advice: str, prompt: str, alpha: bool) -> dict:
    if not alpha:
        prompt = prompt.replace(", PNG.\n", ", PNG or JPEG.\n", 1)
    return {"path": path, "title": title, "size": size, "where": where, "alpha": alpha,
            "formats": "PNG" if alpha else "PNG / JPEG",
            "advice": f"{advice} {ALPHA_NOTE if alpha else OPAQUE_NOTE}".strip(), "prompt": prompt}


def _icon(path: str, name: str, look: str, where: str) -> dict:
    prompt = build_prompt(f"Game icon \"{name}\": {look}, gold and turquoise duotone, soft magical glow", "256×256",
                          "single object centered, filling about 80% of the canvas with even padding, strong silhouette "
                          "readable at 48x48 px, no frame, no letters or numbers", TRANSPARENT)
    return _slot(path, name, "256×256", where, f"Иконка «{name}». Должна читаться в размере 48 px.", prompt, True)


def catalog() -> list[dict]:
    """Every replaceable graphic element of the client, grouped. Each path is read by the client (UI.art)."""
    sec = [
        ("screens", "Экраны и фоны", "Полноэкранные фоны и логотип. Важное держите в центре: на разных телефонах края обрезаются."),
        ("shell", "Верхняя панель и меню", "Фон верхней панели, фон нижнего меню и круглая подложка иконок меню."),
        ("buttons", "Кнопки", "Кнопки растягиваются по ширине текста (9-slice): углы и края должны быть цельными, середина — ровной, без надписей. Углы — 40 px при ширине 360."),
        ("panels", "Панели и карточки", "Окна, карточки и плитки растягиваются (9-slice): орнамент только в углах и по краю, середина спокойная."),
        ("currency", "Иконки валют", "Иконки ресурсов в верхней панели, наградах и инвентаре. 256×256, прозрачный фон."),
        ("icons", "Иконки разделов", "Иконки меню, разделов и кнопок. 256×256, прозрачный фон, крупный силуэт."),
        ("factions", "Эмблемы фракций", "Эмблемы на карточках героев, вкладках и в бою. 256×256, прозрачный фон."),
        ("cards", "Рамки карточек героев", "Рамка поверх портрета героя по редкости. Центр полностью прозрачный, внизу место под имя."),
        ("heroes", "Портреты героев", "Портреты используются в чате, на карточках героев, в бою и в профиле. Квадрат 512×512, герой по пояс, лицо в верхней трети."),
        ("bosses", "Враги и рейд-боссы", "Портреты врагов и боссов для карточек этапов и рейдов. Квадрат 512×512."),
        ("regions", "Регионы похода", "Баннеры глав на экране «Мир». Широкий кадр 1024×320, справа и слева можно обрезать, текст ложится сверху слева."),
        ("battle", "Бой", "Заголовки экрана результата боя."),
        ("story", "Сюжет и обучение", "Портрет рассказчика в сюжетных диалогах."),
        ("shop", "Магазин", "Оформление магазина: табличка, кнопки меню разделов, карточка товара, золотая кнопка цены, лента-метка, баннеры разделов и картинка каждого товара. Карточки и кнопки растягиваются (9-slice)."),
        ("chat", "Оформление чата", "Элементы экрана чата. Рамки и кнопки растягиваются (9-slice), поэтому края и углы должны быть цельными."),
        ("guild", "Знамёна гильдий", "Знамёна гильдий (выбираются в «Управление гильдией» → «Флаг»). Вертикальное знамя на перекладине, прозрачный фон."),
    ]
    sections = [{"id": i, "title": t, "hint": h, "slots": []} for i, t, h in sec]
    by = {x["id"]: x for x in sections}

    # screens
    by["screens"]["slots"] += [
        _slot("ui/boot_bg.png", "Фон стартового экрана", "1080×1920", "экран загрузки и входа",
              "Ключевой арт игры. Верх спокойнее — там логотип, низ закрыт окном входа.",
              build_prompt("Epic vertical key art: Ural mountains at dawn, Toratau shikhan, an ancient fortress, heroic silhouettes, cinematic light",
                           "1080×1920", "vertical poster, main subject in the middle third, top quarter calmer for the logo, bottom third darker for the login window",
                           "full illustration, no transparency"), False),
        _slot("ui/logo.png", "Логотип «Уралия»", "1024×512", "стартовый экран",
              "Табличка под название игры (сам текст можно встроить в картинку).",
              build_prompt("Game logo plate for the title URALIA, golden ornate frame with mountain silhouettes and turquoise gems",
                           "1024×512", "wide plate centered with empty middle space for the title text", TRANSPARENT), True),
        _slot("ui/app_bg.png", "Фон меню", "1080×1920", "фон всех экранов без 3D: Главная, Мир, Ещё, Задания, Настройки, гильдия, чат",
              "Очень тёмный и малоконтрастный: поверх него идут карточки и текст.",
              build_prompt("Dark atmospheric background: night Ural mountains silhouettes, faint Bashkir ornament pattern, subtle turquoise mist",
                           "1080×1920", "uniform vertical background without a focal point, darkest in the middle, very low contrast so cards and text stay readable",
                           "full illustration, no transparency"), False),
    ]
    # shell
    by["shell"]["slots"] += [
        _slot("ui/topbar.png", "Фон верхней панели", "1080×214", "верх каждого экрана: профиль, ресурсы, колокольчик",
              "Растягивается по ширине экрана целиком. Нижний край — тонкая золотая линия.",
              build_prompt("Top bar background strip for a mobile game HUD: dark graphite-teal with a faint ornament, thin polished gold line along the bottom edge",
                           "1080×214", "horizontal strip, evenly dark across the whole width (profile, resource counters and a bell are drawn over it), ornament only along the bottom edge",
                           "opaque, no transparency"), False),
        _slot("ui/navbar.png", "Фон нижнего меню", "1040×180", "нижнее меню из 6 разделов",
              "9-slice, углы 72 px. Шесть кнопок меню рисуются поверх — середина ровная.",
              build_prompt("Bottom navigation bar plate: rounded dark teal glass slab, gold border with small ornaments in the corners",
                           "1040×180", NINE_SLICE, TRANSPARENT), True),
        _slot("ui/nav/bubble.png", "Подложка иконки меню", "256×256", "круг под каждой иконкой нижнего меню",
              "Круглая подложка, центр тёмный и пустой — иконка рисуется поверх.",
              build_prompt("Round medallion socket for a menu icon: dark teal glass disc with a thin gold ring and tiny ornament",
                           "256×256", "circle centered, filling 96% of the canvas, empty dark centre", TRANSPARENT), True),
    ]
    # buttons
    for kind, (title, look, where, text_note) in BUTTONS.items():
        by["buttons"]["slots"].append(_slot(
            f"ui/buttons/{kind}.png", title, "360×120", where,
            "9-slice, углы 40 px. Без текста: подпись кнопки игра рисует сама.",
            build_prompt(f"Mobile game button plate, {look}, rounded rectangle with a subtle bevel and Bashkir ornament in the corners",
                         "360×120", f"{NINE_SLICE}; {text_note}; no text", TRANSPARENT), True))
    # panels
    for code, (title, size, margin, look, where) in PANELS.items():
        by["panels"]["slots"].append(_slot(
            f"ui/panels/{code}.png", title, size, where, f"9-slice, углы {margin} px.",
            build_prompt(_cap(look), size, NINE_SLICE, TRANSPARENT), True))
    # icons
    for kind, (name, look) in CURRENCY_ICONS.items():
        by["currency"]["slots"].append(_icon(f"icons/{kind}.png", name, look, "верхняя панель, награды, инвентарь, магазин"))
    for kind, (name, look) in SECTION_ICONS.items():
        by["icons"]["slots"].append(_icon(f"icons/{kind}.png", name, look, "меню, плитки разделов, кнопки"))
    for kind, (name, look) in FACTION_ICONS.items():
        by["factions"]["slots"].append(_icon(f"icons/{kind}.png", f"Эмблема «{name}»", look, "карточки героев, вкладки фракций, бой"))
    # hero card frames
    for r, (name, look) in RARITY_NAMES.items():
        by["cards"]["slots"].append(_slot(
            f"ui/cards/frame_r{r}.png", f"Рамка: {name}", "460×600", "карточки героев в коллекции, формации, призыве",
            "Растягивается на карточку 230×300 (в 2 раза меньше). Центр прозрачный, нижние 80 px — плашка под имя.",
            build_prompt(f"Ornate hero card frame, {look}, thin border with decorated corners, a small plate along the bottom for the name",
                         "460×600", "frame only along the edges (border about 6% of the width), the whole centre fully transparent so the portrait shows through, "
                         "a dark nameplate band across the bottom 13%", TRANSPARENT), True))
    # heroes / bosses
    for h in D.HEROES:
        enemy = h.get("is_enemy")
        extra = h.get("extra") or {}
        lore = (h.get("lore") or h.get("title") or "")[:160]
        looks = extra.get("appearance", "")
        title_part = f", \"{h['title']}\"" if h.get("title") else ""
        cls = CLASS_EN.get(h.get("class_code", ""), "hero")
        art_ = "an" if cls[:1] in "aeiou" else "a"
        subject = (f"Fantasy character portrait of {h['name']}{title_part}, {art_} "
                   f"{cls} of the {FACTION_EN.get(h.get('faction_code', ''), 'Ural lands')}"
                   + (f". Appearance (Russian description): {looks}" if looks else "")
                   + (". Huge monstrous boss, intimidating" if str(h.get("code", "")).startswith(("rb_", "e_boss")) else ""))
        prompt = build_prompt(subject, "512×512",
                              "bust shot (head and shoulders to waist), character centered, face in the upper third, looking at the viewer, "
                              "nothing important cut by the edges, readable even when shown as a small round avatar",
                              "dark teal gradient with soft gold particles and a subtle rim light, no text")
        by["bosses" if enemy else "heroes"]["slots"].append(_slot(
            f"heroes/{h['code']}.png", h["name"], "512×512", "карточки, чат, бой, профиль, диалоги",
            f"Портрет «{h['name']}». {lore}".strip(), prompt, False))
    # regions
    for r in D.REGIONS:
        look = REGION_LOOKS.get(r["code"], f"landscape of {r['name']} in the Southern Urals")
        by["regions"]["slots"].append(_slot(
            f"regions/{r['code']}.png", r["name"], "1024×320", "экран «Мир» → список регионов (фон карточки главы)",
            f"Глава «{r['name']}» ({r.get('real_place', '')}). Картинка показывается приглушённой под текстом.",
            build_prompt(f"Wide landscape banner: {look}, Southern Urals, Bashkortostan", "1024×320",
                         "panoramic, horizon in the lower half, the top-left area calmer and darker for the chapter title, important details away from the left and right edges",
                         "full illustration, no transparency"), False))
    # battle
    for code, name, look in (("victory", "Заголовок «ПОБЕДА»", "the word ПОБЕДА in Cyrillic, carved gold letters with turquoise glow, laurel wings and a crest"),
                             ("defeat", "Заголовок «ПОРАЖЕНИЕ»", "the word ПОРАЖЕНИЕ in Cyrillic, cracked dark bronze letters with faint red embers, broken sabers")):
        by["battle"]["slots"].append(_slot(
            f"ui/battle/{code}.png", name, "1024×256", "экран результата боя (вместо текстового заголовка)",
            "Надпись должна быть внутри картинки; проверьте, что буквы написаны правильно.",
            build_prompt(f"Game result title banner: {look}", "1024×256", "wide banner, lettering centered and filling 80% of the width",
                         TRANSPARENT, lettering=True), True))
    # story
    by["story"]["slots"].append(_slot(
        "ui/story/narrator.png", "Летописец (рассказчик)", "512×512", "сюжетные диалоги и обучение",
        "Портрет старого мудреца-сказителя, по пояс, смотрит в кадр.",
        build_prompt("Fantasy portrait of an old Bashkir storyteller-chronicler (sesen) with a long grey beard, fur hat, holding a kurai flute and an old book",
                     "512×512", "bust shot, face in the upper third, looking at the viewer", TRANSPARENT), True))
    # shop
    by["shop"]["slots"] += _shop_slots()
    # chat
    for f, title, size, p in CHAT_UI:
        nine = f in ("panel.png", "title_plaque.png", "tab.png", "tab_active.png", "bubble.png", "bubble_mine.png")
        opaque = f.startswith("event_") or f == "background.png"
        comp = NINE_SLICE if nine else ("subject on the right third, left two thirds darker and empty for text" if f.startswith("event_")
                                        else "circular ring centered, ring thickness about 10% of the size, empty center" if f == "avatar_ring.png"
                                        else "vertical scene, no focal object in the middle, very low contrast so text stays readable")
        prompt = build_prompt(_cap(p.split(", transparent background")[0]), size, comp,
                              "dark, no transparency" if opaque else TRANSPARENT)
        by["chat"]["slots"].append(_slot(f"ui/chat/{f}", title, size, "экран чата", f"{title}, {size}.", prompt, not opaque))
    # guild banners
    banners = {"wolf": ("Волк", "teal cloth, a howling wolf head emblem"), "bear": ("Медведь", "crimson cloth, a roaring bear emblem"),
               "eagle": ("Орёл", "royal blue cloth, a golden eagle with spread wings"), "tree": ("Древо", "purple cloth, a sacred tree of life"),
               "horse": ("Конь", "green cloth, a proud horse head (tulpar)"), "stone": ("Гора", "graphite cloth, mountain peaks of the Urals")}
    for code, (name, look) in banners.items():
        prompt = build_prompt(f"Vertical guild war banner on a golden crossbar with finials, {look}, gold trim and Bashkir ornament, "
                              f"swallowtail bottom edge with a small turquoise gem", "512×768",
                              "banner centered, crossbar at the very top, the whole banner visible with even padding", TRANSPARENT)
        by["guild"]["slots"].append(_slot(f"guild/banner_{code}.png", f"Знамя «{name}»", "512×768", "экран гильдии, список гильдий",
                                          f"Знамя гильдии «{name}».", prompt, True))
    return sections


SHOP_SECTION_LOOKS = {
    "crystals": "an open ornate treasure chest overflowing with glowing turquoise crystals in a mountain forest at night",
    "starter": "a golden chest with potions, scrolls and crystals at a campfire near a mountain fortress",
    "resources": "piles of gold coins, green nature essence vials and ore sacks in a fortress storehouse",
    "vip": "a golden crown on a velvet cushion in a throne hall with turquoise light",
    "battlepass": "a war banner on a spear with seasonal ribbons above a valley at dawn",
    "heroes": "silhouettes of legendary heroes in front of the Ural mountains with violet summoning light",
    "cosmetics": "ornate hero portrait frames and a glowing cape on a mannequin in a tailor's tent",
    "seasonal": "an autumn fair with lanterns, golden birch leaves and a festive tent",
}


def _shop_item_look(p: dict) -> str:
    name, sec, sku = p["name"], p["section"], p["sku"]
    if sec == "crystals":
        n = int(sku.rsplit("_", 1)[-1])
        sizes = ["a small handful of", "a leather pouch full of", "a big pouch overflowing with", "a small iron-bound chest of",
                 "a large golden chest overflowing with", "a huge legendary chest bursting with"]
        return f"{sizes[min(n, 6) - 1]} glowing turquoise crystals"
    if sec == "starter":
        return f"a gift chest for \"{name}\" with gold coins, crystals, potions and a scroll, richer for more expensive packs"
    if sec == "resources":
        return f"a supply container for \"{name}\": gold coins, green nature essence vials and ore"
    if sec == "heroes":
        return ("glowing violet hero soul shards" if sku.startswith("shards") else f"a radiant summoning card with a hero silhouette for \"{name}\"")
    if sec == "cosmetics":
        return f"a showcase item for the cosmetic \"{name}\" (frame, title plate, outfit, effect or banner as the name says)"
    if sec == "vip":
        return f"a royal charter scroll with a golden crown seal for the subscription \"{name}\""
    if sec == "battlepass":
        return "a premium battle pass: golden war banner with a crown emblem"
    return f"a festive autumn fair gift for \"{name}\" with golden birch leaves"


def _shop_slots() -> list[dict]:
    from ..monetization.config import cfg as shop_cfg
    sc = shop_cfg()
    out = [
        _slot("ui/shop/title_plaque.png", "Табличка «Магазин»", "880×200", "заголовок магазина (надпись игра рисует сама)",
              "9-slice, края по 60 px. Середина пустая под надпись.",
              build_prompt("Ornate horizontal title plaque: dark teal glass centre, gold frame with pointed diamond ends and turquoise gems",
                           "880×200", NINE_SLICE + "; no text", TRANSPARENT), True),
        _slot("ui/shop/rail.png", "Кнопка раздела (обычная)", "256×200", "левое меню разделов магазина",
              "9-slice, углы 48 px. Иконка и подпись рисуются поверх.",
              build_prompt("Vertical menu button plate: dark teal panel with a thin gold border and small gold diamonds at the top and bottom centre",
                           "256×200", NINE_SLICE + "; no text", TRANSPARENT), True),
        _slot("ui/shop/rail_active.png", "Кнопка раздела (выбрана)", "256×200", "левое меню разделов магазина — активный раздел",
              "9-slice, углы 48 px. Тёплое золотое свечение.",
              build_prompt("Selected vertical menu button plate: warm amber-gold glowing panel, bright gold ornate border, soft outer glow",
                           "256×200", NINE_SLICE + "; no text", TRANSPARENT), True),
        _slot("ui/shop/item_card.png", "Карточка товара", "384×480", "сетка товаров",
              "9-slice, углы 48 px. Картинка товара, количество и кнопка цены рисуются поверх.",
              build_prompt("Product card frame: dark teal panel with a subtle inner glow, gold border with ornamented corners",
                           "384×480", NINE_SLICE, TRANSPARENT), True),
        _slot("ui/shop/price_button.png", "Золотая кнопка цены", "400×100", "кнопка с ценой на каждом товаре",
              "9-slice, края 50 px. Цену игра пишет тёмным текстом — середина светлая и ровная.",
              build_prompt("Gold price button: polished gold capsule with pointed ends and a subtle bevel", "400×100",
                           NINE_SLICE + "; dark text sits on it: keep the middle light and even; no text", TRANSPARENT), True),
        _slot("ui/shop/ribbon.png", "Лента-метка", "256×64", "метки «Выгодно», «Популярно», «−N%» на товарах",
              "9-slice, края 24 px. Текст метки игра пишет белым.",
              build_prompt("Red ribbon tag with a thin gold border and folded ends", "256×64", NINE_SLICE + "; no text", TRANSPARENT), True),
    ]
    for code, title in sc["sections"]:
        look = SHOP_SECTION_LOOKS.get(code, "a treasure display")
        out.append(_slot(f"ui/shop/banner_{code}.png", f"Баннер раздела «{title}»", "1024×360",
                         f"баннер вверху раздела «{title}» с лучшим текущим предложением",
                         "Справа ложатся название, описание и кнопка цены: правая половина темнее и спокойнее.",
                         build_prompt(f"Wide shop banner: {look}", "1024×360",
                                      "main subject in the left 45%, the right half darker and calm for the offer title, text and price button",
                                      "full illustration, no transparency"), False))
    for prod in sc["products"]:
        out.append(_slot(f"ui/shop/items/{prod['sku']}.png", prod["name"], "384×288",
                         f"карточка товара «{prod['name']}» и окно покупки",
                         "Картинка товара без цены и надписей: цену и количество игра пишет сама.",
                         build_prompt(f"Shop item illustration: {_shop_item_look(prod)}", "384×288",
                                      "object centered with a soft glow, filling about 85% of the width, no text, no price, no numbers", TRANSPARENT), True))
    return out


def slot_info(path: str) -> dict | None:
    for sec in catalog():
        for s in sec["slots"]:
            if s["path"] == path:
                return s
    return None


def slot_paths() -> set[str]:
    return {s["path"] for sec in catalog() for s in sec["slots"]}


# ------------------------------------------------------------------ staging
def staging() -> Path:
    p = get_settings().content_store_path / "art_staging"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _index_path() -> Path:
    return staging() / "index.json"


def index() -> dict:
    try:
        return json.loads(_index_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"files": {}, "published_version": 0, "published_at": None}


def _save_index(idx: dict) -> None:
    _index_path().write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")


def image_size(data: bytes) -> tuple[str, int, int] | None:
    """Detects PNG / JPEG / WEBP and returns (format, width, height) from the header (no imaging library)."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) > 24:
        w, h = struct.unpack(">II", data[16:24])
        return "png", w, h
    if data[:3] == b"\xff\xd8\xff":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return "jpg", w, h
            seg = struct.unpack(">H", data[i + 2:i + 4])[0]
            i += 2 + seg
        return "jpg", 0, 0
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        if data[12:16] == b"VP8X":
            w = 1 + int.from_bytes(data[24:27], "little")
            h = 1 + int.from_bytes(data[27:30], "little")
            return "webp", w, h
        return "webp", 0, 0
    return None


def stage(path: str, data: bytes) -> dict:
    info_slot = slot_info(path)
    if info_slot is None:
        raise ValueError("Неизвестный слот графики")
    if len(data) > MAX_BYTES:
        raise ValueError("Файл больше 8 МБ")
    info = image_size(data)
    if info is None:
        raise ValueError("Нужен PNG или JPEG")
    fmt, w, h = info
    if fmt == "webp":
        raise ValueError("WEBP не поддерживается: сохраните картинку как PNG или JPEG")
    if fmt == "jpg" and info_slot["alpha"]:
        raise ValueError("Этому элементу нужен прозрачный фон — загрузите PNG (JPEG не хранит прозрачность)")
    dst = staging() / path
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)
    idx = index()
    idx["files"][path] = {"size": len(data), "width": w, "height": h, "format": fmt, "uploaded_at": utcnow().isoformat(), "published": False}
    _save_index(idx)
    return idx["files"][path]


def unstage(path: str) -> None:
    idx = index()
    if path in idx["files"]:
        (staging() / path).unlink(missing_ok=True)
        del idx["files"][path]
        idx["dirty"] = True
        _save_index(idx)


def staged_file(path: str) -> Path | None:
    p = staging() / path
    return p if path in index()["files"] and p.is_file() else None


def publish(db: Session, admin: str) -> dict:
    """Builds the full ui.art package from every staged file and publishes it to the dev channel."""
    from ..content import pack, service
    idx = index()
    files = {}
    for path in sorted(idx["files"]):
        f = staging() / path
        if f.is_file():
            files[f"art/{path}"] = f.read_bytes()
    from sqlalchemy import func, select
    from ..models import ContentPackageVersion
    last = db.scalar(select(func.max(ContentPackageVersion.version)).where(ContentPackageVersion.package_id == PACKAGE_ID)) or 0
    version = max(int(idx.get("published_version", 0)), int(last)) + 1
    meta = {"package_id": PACKAGE_ID, "version": version, "kind": "ui", "title": "Графика из админ-панели",
            "min_client_version": "0.6.3", "dependencies": [], "required": False}
    if not files:
        files["art/README.txt"] = "Графика из админ-панели пока не загружена.".encode()
    data = pack.build(meta, files)
    pack.validate(data)
    m = service.publish(db, data, channel="dev", notes=f"art v{version}: {len(files)} файлов", admin=admin)
    idx["published_version"] = version
    idx["published_at"] = utcnow().isoformat()
    idx["dirty"] = False
    for v in idx["files"].values():
        v["published"] = True
    _save_index(idx)
    return {"version": version, "files": len(files), "manifest": m.version}
