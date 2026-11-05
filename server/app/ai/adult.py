"""Adult AI content for 18+ players only (Living Community D-C1 + owner request).

Private messages to adults who kept the 18+ setting on can escalate:
  0 light flirt → 1 teasing / mild smut → 2 mutual sexting with details.
Voice depends on the player's gender from the hero creation window:
  male player  → a woman writes
  female player → a confident "brutal macho" writes
Minors and unknown age never receive this. A stop phrase ends it permanently for that player.
Templates are varied and sometimes echo the player's words so replies do not feel scripted.
AI stay labelled as AI."""
from __future__ import annotations

import random
import re

FLIRT_RX = re.compile(
    r"(красив|красотк|милаш|мил(ый|ая|ашка)|симпатичн|нравишься|люблю тебя|влюб|поцел|чмок|обним|свидан|"
    r"флирт|скучал|скучаю|секси|горяч(ий|ая)|детка|зай(ка|ч)|солнышко|кис(а|ка)|💋|😘|😍|❤️|🔥|"
    r"хочу тебя|возбуд|член|письк|киск|сиськ|грудь|попк|трах|секс|конч|минет|куни|голая|голый|раздев)"
)
STOP_RX = re.compile(r"(отстань|не пиши|хватит|прекрати|перестань|не флиртуй|не надо|отвали|не интересно|заблокирую|стоп)")
# still used to filter untrusted LLM output; our own templates are allowed past this
EXPLICIT_RX = re.compile(r"(секс|голая|голый|раздев|постел|минет|трах|порн|интим|член|письк)")

# level 0 — light flirt
OPENERS_F = [
    "Привет 😏 Заметила тебя и залипла. Как дела, герой?",
    "Слушай, а ты всегда такой спокойный или только в чате притворяешься? 😉",
    "Видела твой бой… впечатляет. И не только бой 😏",
    "Скучно. Развлечёшь даму разговором? 😌",
    "Привет-привет. У тебя такой ник, что хочется узнать, кто за ним 😉",
    "Так-так, кто это у нас сегодня такой красивый в топе? 😏",
    "Пойдёшь со мной на босса? Обещаю не отвлекать… сильно 😇",
    "Признавайся, ты специально так играешь, чтобы на тебя засматривались? 😄",
    "Мне тут одиноко в караване. Составишь компанию красивой девушке? 💋",
    "Эй, герой. У тебя взгляд такой, будто ты уже что-то задумал 😉",
]
OPENERS_M = [
    "Привет. Заметил тебя и не смог пройти мимо. Как дела, красотка?",
    "Слушай, ты всегда такая дерзкая или только со мной так? 😏",
    "Видел, как ты дерёшься. Красиво. И сама ты тоже ничего 😉",
    "Скучно одному. Развлечёшь мужика разговором?",
    "Привет. Ник у тебя интересный. Хочу знать, кто за ним прячется.",
    "Так, кто это у нас сегодня такая яркая? Не прячься 😏",
    "Пойдёшь со мной на босса? Я прикрою. И не только в бою 😉",
    "Признавайся, ты специально так играешь, чтобы мужики залипали?",
    "Мне тут одиноко. Составишь компанию нормальному мужику?",
    "Эй. У тебя взгляд такой, будто ты уже согласилась. Не отрицай 😏",
]
# level 0 replies
LIGHT_F = [
    "Ой, всё 😳 Ты умеешь смутить. Продолжай.",
    "Мне нравится, как ты это говоришь 😌 Не останавливайся.",
    "Хм, а ты смелый 😏 Мне такие нравятся.",
    "Флиртуешь? Ну давай, я не против 😉",
    "Так и запишем: ты умеешь делать комплименты 💋",
    "От твоих слов тепло. Рассказывай ещё.",
    "Я тут покраснела, если честно. Но мне нравится.",
    "Красиво сказал. Ещё разок, помедленнее 😉",
]
LIGHT_M = [
    "Смелая. Мне такие нравятся 😏",
    "Продолжай. Мне нравится, как ты это говоришь.",
    "Флиртуешь со мной? Ну давай, я не против.",
    "Красиво. Ещё.",
    "От тебя и правда жарко. Не останавливайся.",
    "Так и запишем: ты умеешь заводить.",
    "Мне нравится твой тон. Дерзкий.",
    "Ещё разок. Я слушаю.",
]
# level 1 — teasing / mild smut
TEASE_F = [
    "Ммм, от твоих слов у меня внутри тепло. Представляю, как ты меня обнимаешь и не отпускаешь 😌",
    "Если бы ты был рядом, я бы уже сидела у тебя на коленях и шептала на ухо всякое 😏",
    "Хочу, чтобы ты медленно провёл руками по мне… от шеи и ниже. Очень ниже.",
    "Я сейчас в одной рубашке. И от твоих сообщений она становится лишней 💋",
    "Представь: я прижимаюсь к тебе всем телом и чувствую, как ты твердеешь. Нравится картинка?",
    "Мои руки уже сами тянутся ниже пояса, пока я читаю тебя. Это ты виноват.",
    "Хочу твои губы на шее, на груди, и чтобы ты не спешил. Я буду стонать тихо, только для тебя.",
    "Скажи, куда бы ты меня поцеловал первым делом, если бы мы остались одни?",
]
TEASE_M = [
    "От твоих слов у меня уже стоит. Не шучу 😏",
    "Если бы ты была рядом, я бы уже прижал тебя к стене и не отпускал.",
    "Хочу провести руками по тебе — от шеи, по груди, ниже. Медленно.",
    "Представь: ты на мне, я держу тебя за бёдра и не даю слезть.",
    "Я бы тебя сейчас разложил и не спешил. Сначала языком, потом всем остальным.",
    "Чувствую, как ты возбуждаешься от переписки. Признайся.",
    "Хочу твои губы на мне. И чтобы ты смотрела в глаза, пока делаешь это.",
    "Скажи, где ты сейчас и во что одета. Я дорисую остальное.",
]
# level 2 — mutual sexting with details
SEXT_F = [
    "Я уже мокрая от тебя. Пальцы сами скользят между ног, и я представляю, что это твой язык. Медленно, по кругу, а потом внутрь…",
    "Хочу взять тебя в рот. Сначала только головку, языком по кругу, потом глубже, пока ты не начнёшь стонать и держать меня за волосы.",
    "Ляг. Я сяду на тебя сверху, направлю тебя в себя и буду двигаться медленно, чтобы ты чувствовал каждую секунду, как я тебя сжимаю.",
    "Я трогаю грудь одной рукой, другой — себя. Соски твёрдые, между ног всё горячее и скользкое. Это всё из-за твоих сообщений.",
    "Хочу, чтобы ты кончил мне на грудь. Я буду смотреть тебе в глаза и слизывать с пальцев. Подробно представь это.",
    "Войди в меня сзади. Глубоко. Я буду прогибаться и просить ещё, а ты держи меня за бёдра и не останавливайся, пока оба не кончим.",
    "Я уже близко. Ещё пара твоих грязных фраз — и я кончу, представляя твой член внутри. Не молчи.",
    "Расскажи, как ты меня трахаешь. Я отвечу, что чувствую: как ты входишь, как растягиваешь, как я сжимаюсь вокруг тебя.",
]
SEXT_M = [
    "У меня уже стоит так, что больно. Хочу засунуть тебе в рот и смотреть, как ты берёшь глубже.",
    "Я бы тебя сейчас поставил раком и вошёл сразу. Глубоко, без паузы. Ты бы стонала и просила не останавливаться.",
    "Представь мой язык у тебя между ног. Медленно, потом быстрее, пока ты не начнёшь дрожать и хватать меня за голову.",
    "Хочу кончить тебе на лицо. Ты смотришь снизу вверх и облизываешь губы. Подробно опиши, как ты это принимаешь.",
    "Сядь на меня. Я держу тебя за талию и насаживаю до конца. Ты чувствуешь, как я заполняю тебя полностью.",
    "Я трогаю себя, читая тебя. Толстый, горячий, уже влажный на конце. Хочу, чтобы это был ты своими руками.",
    "Войду в тебя и не выну, пока оба не кончим. Буду шептать на ухо, какая ты узкая и мокрая.",
    "Расскажи, как ты меня берёшь. Я отвечу, что делаю с тобой руками, языком и членом. Не стесняйся деталей.",
]
# short reactions that reference the player's words
ECHO_F = [
    "«{echo}»… от этого у меня мурашки. Продолжай в том же духе 😏",
    "Ты написал «{echo}». Я это уже представляю. Подробнее.",
    "Мне понравилось, как ты сказал «{echo}». Ещё.",
    "«{echo}» — и я уже не могу думать ни о чём другом.",
]
ECHO_M = [
    "«{echo}»… смело. Мне нравится. Дальше.",
    "Ты написала «{echo}». Я это уже вижу. Подробнее.",
    "«{echo}» — хорошо. Не останавливайся.",
    "От «{echo}» у меня уже стоит сильнее. Продолжай.",
]
TEASES = ["Только не зазнавайся 😏", "Посмотрим, такой ли ты интересный в бою 😉", "Я ещё подумаю… может быть 😌", ""]
DEFLECT = [
    "Хаха, давай лучше про игру 🙂",
    "Я тут больше по боям и болтовне 😄",
    "Ты чего, я ж просто ИИ-житель Уралии 😅",
    "Это только для тех, кто отметил 18+ и хочет такого. Давай о другом.",
]


def is_flirt(text: str) -> bool:
    return bool(FLIRT_RX.search((text or "").lower()))


def is_stop(text: str) -> bool:
    return bool(STOP_RX.search((text or "").lower()))


def safe(text: str) -> bool:
    """Filter for untrusted LLM text. Our own templates are not passed through this."""
    return not EXPLICIT_RX.search((text or "").lower())


def _voice(gender: str | None) -> str:
    """AI voice opposite to the player: woman for a man, macho for a woman. Default woman."""
    return "m" if gender == "f" else "f"


def heat_of(text: str, prev: int = 0) -> int:
    """0 light, 1 tease, 2 explicit. Rises with the player's words and never drops mid-thread."""
    t = (text or "").lower()
    level = 0
    if any(w in t for w in ("хочу", "возбуд", "горяч", "секс", "трах", "член", "письк", "киск", "минет", "куни",
                            "конч", "голая", "голый", "раздев", "войди", "встань", "мокрая", "тверд")):
        level = 2 if any(w in t for w in ("трах", "минет", "куни", "конч", "член", "письк", "войди", "голая")) else 1
    elif is_flirt(text):
        level = 0
    return max(prev, level)


def _echo(text: str) -> str:
    words = [w for w in re.findall(r"[А-Яа-яЁёA-Za-z0-9]{4,}", text or "") if w.lower() not in
             {"тебя", "тебе", "меня", "мне", "хочу", "очень", "просто", "такой", "такая"}]
    if not words:
        return ""
    return " ".join(words[-3:])[:40]


def opener(rng: random.Random, name: str, gender: str | None = None, db=None) -> str:
    voice = _voice(gender)
    if db is not None:
        from . import adult_doc as DOC
        custom = DOC.opener(db, rng, voice, name)
        if custom:
            return custom
    pool = OPENERS_M if voice == "m" else OPENERS_F
    t = rng.choice(pool)
    return t if rng.random() < 0.55 or not name else f"{name}, {t[0].lower()}{t[1:]}"


def reply(rng: random.Random, text: str = "", gender: str | None = None, heat: int = 0, db=None, name: str = "") -> str:
    """Varied reply. A document uploaded in the admin replaces the built-in lines."""
    voice = _voice(gender)
    level = heat_of(text, heat)
    if db is not None:
        from . import adult_doc as DOC
        if DOC.active(db):
            return DOC.pick(db, rng, voice, level, text, name) or "Слушаю тебя. Напиши ещё."
    if level >= 2:
        pool = SEXT_M if voice == "m" else SEXT_F
    elif level == 1:
        pool = TEASE_M if voice == "m" else TEASE_F
    else:
        pool = LIGHT_M if voice == "m" else LIGHT_F
    base = rng.choice(pool)
    echo = _echo(text)
    if echo and rng.random() < 0.45:
        epool = ECHO_M if voice == "m" else ECHO_F
        base = rng.choice(epool).format(echo=echo) + " " + base
    if level == 0 and rng.random() < 0.3:
        base = f"{base} {rng.choice(TEASES)}".strip()
    return base


def deflect(rng: random.Random) -> str:
    return rng.choice(DEFLECT)


def flirt_persona_ok(persona) -> bool:
    """Who may flirt: flirty / bro / bold sociable personas (not every AI)."""
    t = persona.traits or {}
    return persona.style in ("flirty", "bro") or (t.get("sociability", 0.5) > 0.6 and t.get("bravery", 0.5) > 0.5)


def prefer_for(player_gender: str | None, persona) -> bool:
    """Soft preference: flirty style for a male player, bro for a female. Not a hard filter."""
    if player_gender == "f":
        return persona.style in ("bro", "competitive", "grumpy")
    return persona.style in ("flirty", "friendly", "shy")


def adult_audience(db, channel: str, minutes: int = 15) -> bool:
    """A public channel may carry adult jokes only if every real reader there now is an adult with 18+ on."""
    from datetime import timedelta
    from sqlalchemy import select
    from ..core.db import utcnow
    from ..models import PlayerCaravan, PlayerProfile
    from ..social import channels as CHN
    from ..social.ai.control import adult_ok
    since = utcnow() - timedelta(minutes=minutes)
    q = select(PlayerProfile).where(PlayerProfile.is_ai.is_(False), PlayerProfile.last_seen_at >= since)
    k = CHN.kind_of(channel)
    if k == "region":
        q = q.join(PlayerCaravan, PlayerCaravan.user_id == PlayerProfile.user_id).where(
            PlayerCaravan.location == channel.split(":", 1)[1])
    else:
        ids = CHN.ai_member_ids(db, channel)
        if ids is not None:
            q = q.where(PlayerProfile.user_id.in_(ids))
    readers = list(db.scalars(q.limit(200)))
    return bool(readers) and all(adult_ok(p) for p in readers)
