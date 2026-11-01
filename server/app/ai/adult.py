"""Adult AI content for 18+ players (Living Community decision D-C1, approved by the owner).

Flirt, compliments and innuendo from AI residents — in public channels only when every real reader there is an adult
with the 18+ setting on, and in private messages only to such adults. Never: minors or unknown age, graphic sexual
descriptions, coercion, pressure to spend money, continuing after the player says stop. AI stay labelled as AI."""
from __future__ import annotations

import random
import re

FLIRT_RX = re.compile(r"(красив|красотк|милаш|мил(ый|ая|ашка)|симпатичн|нравишься|люблю тебя|влюб|поцел|чмок|обним|свидан|"
                      r"флирт|скучал|скучаю|секси|горяч(ий|ая)|детка|зай(ка|ч)|солнышко|кис(а|ка)|💋|😘|😍|❤️|🔥)")
STOP_RX = re.compile(r"(отстань|не пиши|хватит|прекрати|перестань|не флиртуй|не надо|отвали|не интересно|заблокирую|стоп)")
EXPLICIT_RX = re.compile(r"(секс|голая|голый|раздев|постел|минет|трах|порн|интим)")  # never in AI output

OPENERS = [
    "Привет 😏 Шла мимо твоего профиля и залипла. Как дела, герой?",
    "Слушай, а ты всегда такой загадочный или только в чате? 😉",
    "Видела твой бой на арене… впечатляет. И не только бой 😏",
    "Скучно сегодня. Развлечёшь даму разговором? 😌",
    "Привет-привет 🙂 У тебя такой ник, что хочется узнать, кто за ним прячется 😉",
    "Так-так, кто это у нас сегодня такой красивый в топе? 😏",
    "Пойдёшь со мной на босса? Обещаю не отвлекать… сильно 😇",
    "Признавайся, ты специально так круто играешь, чтобы на тебя засматривались? 😄",
]
REPLIES = [
    "Ой, всё 😳 Ты умеешь смутить.", "Продолжай, мне нравится, как ты это говоришь 😌", "Хм, а ты смелый 😏 Мне такие нравятся.",
    "Осторожнее, я ведь могу и привыкнуть к таким словам 😉", "Комплименты принимаются. Можно ещё 😄",
    "Ты всегда такой милый или только со мной? 😊", "Ну всё, теперь буду думать о тебе на каждом бою 😅",
    "Опасный ты человек… в хорошем смысле 😏", "Ммм, интригуешь. Рассказывай дальше 😉",
]
TEASES = ["Только не зазнавайся 😏", "Посмотрим, такой ли ты интересный в бою 😉", "Я ещё подумаю… может быть 😌", ""]
DEFLECT = ["Хаха, давай лучше про игру 🙂", "Я тут больше по боям и болтовне 😄", "Ты чего, я ж просто ИИ-житель Уралии 😅"]


def is_flirt(text: str) -> bool:
    return bool(FLIRT_RX.search((text or "").lower()))


def is_stop(text: str) -> bool:
    return bool(STOP_RX.search((text or "").lower()))


def safe(text: str) -> bool:
    return not EXPLICIT_RX.search((text or "").lower())


def opener(rng: random.Random, name: str) -> str:
    t = rng.choice(OPENERS)
    return t if rng.random() < 0.6 or not name else f"{name}, {t[0].lower()}{t[1:]}"


def reply(rng: random.Random) -> str:
    r = rng.choice(REPLIES)
    tail = rng.choice(TEASES)
    return f"{r} {tail}".strip()


def deflect(rng: random.Random) -> str:
    return rng.choice(DEFLECT)


def flirt_persona_ok(persona) -> bool:
    """Who flirts: personas with a flirty style or a sociable, bold character (not every AI)."""
    t = persona.traits or {}
    return persona.style == "flirty" or (t.get("sociability", 0.5) > 0.6 and t.get("bravery", 0.5) > 0.5)


def adult_audience(db, channel: str, minutes: int = 15) -> bool:
    """A public channel may carry adult jokes only if every real reader there now is an adult with 18+ on (and there is
    at least one reader)."""
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
