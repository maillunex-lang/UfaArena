"""AI-to-AI chat: multi-turn conversations between personas so the chat is never empty — banter, arguments,
jokes, flirting, tips, newbie questions. Casual gamer tone, no profanity (the chat filter masks it anyway).

Arguments and flirting happen only between AI personas; replies to real players stay friendly (dialogue.py).
Lines are queued with human-like delays and posted by the AI tick; volume is capped per hour."""
from __future__ import annotations

import random
import re
import time
from collections import deque

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...core.db import utcnow
from ...models import AiPersona, ChatMessage, GuildMember, PlayerProfile

HEROES = ["Арслан-Кара", "Бай-Таш", "Сафарий", "Ай-Тулган", "Юрек", "Сумбэль", "Ак-Буре", "Тан-Чечек", "Варгат", "Морай",
          "Зархан", "Ур-Каан", "Азамат", "Хумай", "Айгуль"]
FACTIONS = ["Каменное Небо", "Живой Курай", "Пепельный Предел"]
BOSSES = ["Аждаха", "Курганный Колосс", "Древний Корень", "Тень Шульгана"]
PLACES = ["Иремель", "Шульган-Таш", "Торатау", "Нугуш", "Янгантау", "Зилаир", "Агидель", "Юрактау"]
FOODS = ["чак-чак", "бешбармак", "кумыс", "баурсаки", "мёд", "эчпочмак", "казы", "блины с мёдом"]

# Each script: weight, number of roles, preferred styles per role, turns [(role, [variants...])].
# Placeholders: {A} {B} {C} nicknames, {hero} {hero2} {faction} {faction2} {boss} {place} {food} {num} {big} {lvl}
SCRIPTS: list[dict] = [
    {"w": 5, "roles": 2, "pref": {"A": ["competitive", "grumpy"], "B": ["joker", "humorous"]}, "turns": [
        ("A", ["Кто опять мне защиту на арене снёс? Признавайтесь 😤", "Арена сегодня — чистый рандом, я в шоке",
               "Минус {num} рейтинга за вечер. Я ухожу из этой игры. До завтра 😑"]),
        ("B", ["@{A} это был я, извини, ты просто удобно стоял 😂", "@{A} зато какая стабильность, всё время вниз",
               "@{A} да ладно, у тебя защита как у Колосса… картонного 😅"]),
        ("A", ["@{B} очень смешно. Реванш через пять минут", "@{B} я тебя запомнил, жди в гости", "@{B} смейся-смейся, клоун 🤡"]),
        ("B", ["@{A} жду, чай заварил ☕", "@{A} давай-давай, только лекаря не забудь в этот раз", "@{A} го, только без слёз потом"]),
    ]},
    {"w": 5, "roles": 2, "pref": {"A": ["friendly", "bro"], "B": ["humorous", "joker"]}, "turns": [
        ("A", ["Сделал 10 призывов. Угадайте, сколько легенд 🙃", "Призыв меня сегодня ненавидит", "Ну хоть {hero} выпал, уже праздник"]),
        ("B", ["@{A} ноль? Классика, добро пожаловать в клуб 😂", "@{A} у меня вообще десять одинаковых лиц пришло",
               "@{A} гарант на 60-м, держись, бро"]),
        ("A", ["@{B} ну хоть осколки копятся, звёзды будут", "@{B} ещё пара призывов — и я точно сломаю систему", "@{B} спасибо, утешил как мог 😅"]),
    ]},
    {"w": 4, "roles": 3, "pref": {"A": ["competitive"], "B": ["wise", "strategist"], "C": ["grumpy", "laconic"]}, "turns": [
        ("A", ["Кто сейчас имба на арене? Хочу перестроить защиту", "Варгат вообще играет или это мем?", "Что ставить против Пепельного Предела?"]),
        ("B", ["@{A} смотри по фракциям: {faction} бьёт {faction2} на 20%, это решает", "@{A} {hero} в центр, {hero2} назад — и уже норм",
               "@{A} танк спереди, урон сзади, лекарь в углу. База, без неё никуда"]),
        ("C", ["Да всё имба, если прокачано. Качайтесь, а не меты ищите", "@{B} ну началась лекция по тактике 🙄", "{hero} переоценён, моё мнение"]),
        ("B", ["@{C} переоценён, пока он тебе защиту не снесёт 😏", "@{C} лекция бесплатная, пользуйся", "@{C} а ты что ставишь, умник?"]),
        ("C", ["@{B} я ставлю всё, что прокачано. Работает же", "@{B} ладно-ладно, принято", "@{B} секрет фирмы 🤫"]),
    ]},
    {"w": 4, "roles": 2, "pref": {"A": ["flirty"], "B": ["shy", "flirty", "friendly"]}, "turns": [
        ("A", ["@{B} привет, красота 😏 как твой отряд сегодня?", "@{B} ты опять в топе урона по боссу, это вообще законно? 🔥",
               "@{B} пойдёшь со мной на {boss}? Вдвоём веселее 😉"]),
        ("B", ["@{A} ой, всё 😳", "@{A} отряд в порядке, а вот ты что-то разговорчивый сегодня 😄", "@{A} пойду, если лекаря возьмёшь, а не только комплименты"]),
        ("A", ["@{B} для тебя хоть двух лекарей 💐", "@{B} я просто констатирую факты 😌", "@{B} тогда до встречи у {place} на закате"]),
        ("B", ["@{A} посмотрим-посмотрим 😊", "@{A} ну ты и болтун 😂 ладно, го", "@{A} только не опаздывай, батыр 😉"]),
    ]},
    {"w": 3, "roles": 3, "pref": {"A": ["flirty"], "B": ["friendly", "shy"], "C": ["joker", "humorous"]}, "turns": [
        ("A", ["@{B} а ты всегда так красиво босса бьёшь или только при мне? 😏", "@{B} твой {hero} сегодня огонь, как и ты 🔥"]),
        ("C", ["Опять {A} подкатывает, народ, засекайте время ⏱️", "@{A} бро, это общий чат, а не свидание 😂"]),
        ("B", ["@{C} ахах, пусть старается 😄", "@{A} спасибо 😊 @{C} не мешай человеку"]),
        ("A", ["@{C} завидуй молча 😎", "@{C} у тебя просто нет вкуса"]),
    ]},
    {"w": 4, "roles": 2, "pref": {"A": ["shy", "friendly"], "B": ["friendly", "wise", "bro"]}, "turns": [
        ("A", ["Народ, я новичок, застрял на главе {num}. Что делать?", "Подскажите, куда тратить эссенцию природы?", "Как вообще попасть в гильдию?"]),
        ("B", ["@{A} качай героев, улучшай кузню в крепости и собирай AFK каждые пару часов — пройдёшь",
               "@{A} эссенцию — на уровни основных пятерых, остальных не трогай пока",
               "@{A} Режимы → Гильдия → Найти. ИИ-гильдии берут всех, да и живые тоже"]),
        ("A", ["@{B} спасибо, бро! Попробую 🙏", "@{B} о, точно, а я про кузню вообще забыл", "@{B} понял, принял, бегу"]),
        ("B", ["@{A} пиши, если что, поможем", "@{A} не за что, удачи! И друзей добавляй — подарки каждый день", "@{A} давай, жду в топе 😉"]),
    ]},
    {"w": 4, "roles": 2, "pref": {"A": ["grumpy", "competitive"], "B": ["grumpy", "competitive", "laconic"]}, "turns": [
        ("A", ["{faction} — лучшая фракция, и не спорьте", "Кто играет без танка, тот сам себе враг", "Живой Курай — это для тех, кто боится драться"]),
        ("B", ["@{A} ага, конечно. {faction2} вас разносит и не замечает", "@{A} опять ты со своей фракцией…", "@{A} сказал человек, которого вчера я на арене уронил"]),
        ("A", ["@{B} это был случайный крит, не обольщайся", "@{B} давай на арене решим, без болтовни", "@{B} ну-ну, рассказывай"]),
        ("B", ["@{A} случайный? Три раза подряд? 😂", "@{A} в любое время, батыр", "@{A} ладно, без обид, просто ты не прав 😏"]),
        ("A", ["@{B} ладно, мир. Пока что 🤝", "@{B} посмотрим, кто будет смеяться в конце сезона", "@{B} ой всё"]),
    ]},
    {"w": 3, "roles": 3, "pref": {"A": ["veteran", "wise"], "B": ["friendly"], "C": ["humorous"]}, "turns": [
        ("A", ["Гильдия набирает! Задания каждый день, босс по расписанию, без токсиков", "Кто без гильдии — к нам, места есть"]),
        ("B", ["@{A} а что по требованиям?", "@{A} а босса реально бьёте или для галочки?"]),
        ("A", ["@{B} заходи хоть с первого уровня, главное — активность", "@{B} бьём каждый день, вчера Колосса до трети уронили"]),
        ("C", ["@{A} а печеньки дают? 🍪", "Лишь бы не как в прошлой, где глава три недели спал 😂"]),
        ("A", ["@{C} печеньки по пятницам 😄", "@{C} у нас глава не спит, проверено"]),
    ]},
    {"w": 4, "roles": 2, "pref": {"A": ["humorous", "joker"], "B": ["friendly", "humorous", "bro"]}, "turns": [
        ("A", ["Мой лекарь сегодня решил стать танком. Встал вперёд и героически лёг 😂",
               "Поставил всех пятерых в первый ряд. Тактика «в лоб». Угадайте результат",
               "Перепутал отряд для арены и для босса. Колосс был в восторге"]),
        ("B", ["@{A} 😂😂 классика", "@{A} зато смело!", "@{A} это не баг, это стиль игры", "@{A} смешно, но я так же вчера сделал 🙈"]),
        ("A", ["@{B} хоть кто-то меня понимает", "@{B} вот и я говорю — авторский подход", "@{B} брат по несчастью 🤝"]),
    ]},
    {"w": 3, "roles": 2, "pref": {"A": ["friendly", "bro"], "B": ["humorous", "joker"]}, "turns": [
        ("A", ["Кто что ест, пока фармит? Я {food} 😋", "Сижу с {food}, качаю героев. Идеальный вечер", "Обед — святое, но AFK-сундук ждать не будет"]),
        ("B", ["@{A} {food}, конечно, что ещё 😄", "@{A} я бы тоже, но у меня только сухарики", "@{A} не дразни, я на диете 😭"]),
        ("A", ["@{B} приходи в крепость, угощу 😂", "@{B} держись, батыр", "@{B} эх, жизнь"]),
    ]},
    {"w": 3, "roles": 3, "pref": {"A": ["competitive"], "B": ["laconic", "grumpy"], "C": ["joker"]}, "turns": [
        ("A", ["Сегодня ночью снесу всех в Золотой лиге. Предупредил 😎", "Кто в топ-10 арены? Готовьтесь, иду"]),
        ("B", ["@{A} мечтать не вредно", "@{A} с твоей защитой? 🙂", "@{A} иди-иди"]),
        ("C", ["Ставлю {num} кристаллов, что не снесёт 😂", "Запасаемся попкорном 🍿"]),
        ("A", ["@{C} ставку принял, готовь кристаллы", "@{B} @{C} утром поговорим 😤"]),
    ]},
    {"w": 3, "roles": 2, "pref": {"A": ["wise", "friendly"], "B": ["shy", "friendly"]}, "turns": [
        ("A", ["Кто был на {place}? Говорят, на рассвете там очень красиво", "Говорят, в {place} спрятано что-то древнее. Кто проверял?"]),
        ("B", ["@{A} был! Там такие виды, жаль, в бою не до них", "@{A} я слышал, что там видели следы Шульгана 😨"]),
        ("A", ["@{B} может, следующая глава туда приведёт", "@{B} летопись мира скоро ответит"]),
    ]},
    {"w": 3, "roles": 3, "pref": {"A": ["friendly"], "B": ["competitive"], "C": ["humorous"]}, "turns": [
        ("A", ["Народ, событие «{event}» идёт — давайте дожмём цель, награда всем!", "{event}: прогресс сервера ползёт. Делаем бои события!"]),
        ("B", ["@{A} я уже {big} очков вкинул, ваша очередь", "@{A} в топе вклада пока я, догоняйте 😏"]),
        ("C", ["@{B} хвастун 😂 ладно, иду делать бои", "А если не дожмём — Тьма опять всё опалит, как в прошлый раз?"]),
        ("A", ["@{C} вот именно, так что все на бой!", "@{B} уважение 💪"]),
    ]},
    {"w": 3, "roles": 2, "pref": {"A": ["grumpy"], "B": ["joker", "friendly"]}, "turns": [
        ("A", ["Почему у босса опять фаза ярости, когда я захожу? Заговор какой-то", "Аждаха меня ненавидит лично"]),
        ("B", ["@{A} она всех ненавидит, не принимай на свой счёт 😂", "@{A} смотри уязвимость фазы, там же написано, к кому слабее"]),
        ("A", ["@{B} читать — это для слабых 😤", "@{B} ну ладно, посмотрю… может быть"]),
        ("B", ["@{A} ну вот и разобрались 😄", "@{A} потом спасибо скажешь"]),
    ]},
    {"w": 2, "roles": 2, "pref": {"A": ["flirty"], "B": ["grumpy", "laconic"]}, "turns": [
        ("A", ["@{B} а ты чего такой хмурый? Улыбнись, тебе идёт 😉", "@{B} привет-привет, батыр 😏"]),
        ("B", ["@{A} я не хмурый, я сосредоточенный", "@{A} нет", "@{A} иди босса бей лучше 🙄"]),
        ("A", ["@{B} ну и ладно, всё равно ты милый 😌", "@{B} эх, суровый какой 😂"]),
    ]},
    {"w": 3, "roles": 2, "pref": {"A": ["bro", "friendly"], "B": ["bro", "friendly", "competitive"]}, "turns": [
        ("A", ["Ура! {hero} наконец ★{num}! 🎉", "Поднял {hero} до {lvl} уровня, теперь он реально тащит", "Выбил «Сердце кургана» с Колосса, кто ещё фартовый?"]),
        ("B", ["@{A} красавчик! 💪", "@{A} поздравляю, бро! Теперь на арене берегись", "@{A} завидую белой завистью 😭"]),
        ("A", ["@{B} спасибо! Пошёл проверять на арене", "@{B} го вместе на босса теперь", "@{B} и тебе скоро повезёт!"]),
    ]},
    {"w": 2, "roles": 2, "pref": {"A": ["humorous", "joker"], "B": ["wise", "laconic"]}, "turns": [
        ("A", ["Философский вопрос: если AFK-сундук копится, когда я сплю, то я играю или нет? 🤔",
               "Кто придумал, что Колосс должен бить так больно? Это нечестно, у меня лапки 🐾"]),
        ("B", ["@{A} играешь. Сундук не врёт", "@{A} лапки не оправдание 😄", "@{A} глубоко…"]),
        ("A", ["@{B} значит, я профессионал 😎", "@{B} ну всё, расскажу всем"]),
    ]},
]

AMBIENT: dict[str, list[str]] = {
    "any": [
        "Всем вечер в Курултае! 🏔️", "Кто на босса гильдии? Го, нас трое уже", "Опять Колосс крит прокинул, ну за что 😩",
        "AFK-сундук — лучший друг хранителя", "Фармлю главу {num}, кто со мной по чату за компанию?", "У кого есть лишний лекарь? Шучу, их не бывает",
        "Сегодня какой-то фартовый день, третий раз подряд выиграл на арене 😎", "Кто-нибудь понял, как работает метка Юрека? Я пока нет",
        "{hero} — недооценённый герой, отвечаю", "Кто идёт к {place}? Пишите", "Только что поднял героя до {lvl} уровня, ура!",
        "Обожаю, когда весь отряд выживает. Редкий кайф", "Мой {hero} сегодня тащит как не в себя", "Кумыс налит, бой начат 🥛",
        "Народ, не забывайте собирать подарки от друзей — жетоны сами себя не потратят", "Ночной фарм — самый честный фарм 🌙",
        "Кто в Серебряной лиге — давайте дружить, вместе веселее", "Колосс в фазе «Трещины», маги, вперёд!", "Хочу ещё одну главу кампании, срочно 😅",
    ],
    "grumpy": ["Арена сегодня издевается", "Кто балансил этого босса, признавайтесь", "Опять проиграл с перевесом в силе. Рандом, спасибо 😑",
               "Почему все ставят одних и тех же героев? Скука"],
    "joker": ["Мой отряд в ударе. Ну то есть его бьют 😂", "Потерял лекаря. Если найдёте — верните, он пугливый",
              "Сделал всё по гайду. Гайд оказался про другую игру 🤡", "Играю так плохо, что Колосс меня уже жалеет"],
    "flirty": ["Кто на совместную охоту? Желательно симпатичные 😏", "В Курултае сегодня столько интересных людей 😉",
               "Ищу напарника на {boss}. Можно и не только на босса 😌"],
    "wise": ["Не спешите. Уралия никуда не денется", "Сила отряда — не только уровень. Фракции и расстановка решают больше",
             "Говорят, если долго смотреть на Торатау, она посмотрит в ответ"],
    "competitive": ["+{num} рейтинга за вечер. Кто следующий?", "Ищу соперников в Золотой лиге", "Защита обновлена. Попробуйте пробить 😏"],
    "shy": ["Привет всем 🙂", "Я сегодня первый раз прошёл главу без поражений!", "Кто-нибудь ходил к Иремелю? Красиво там?"],
}

_queue: deque = deque(maxlen=400)  # (due_monotonic, persona_user_id, channel, text)
_rng = random.Random()
_last_start = 0.0


def _fill(text: str, names: dict, extra: dict) -> str:
    vals = {**extra, **names}

    def rep(m: re.Match) -> str:
        return str(vals.get(m.group(1), m.group(0)))
    return re.sub(r"{(\w+)}", rep, text)


def _ctx(db: Session) -> dict:
    from ...models import WorldEvent
    ev = db.scalar(select(WorldEvent).where(WorldEvent.status == "active").order_by(WorldEvent.starts_at.desc()))
    f1, f2 = _rng.sample(FACTIONS, 2)
    h1, h2 = _rng.sample(HEROES, 2)
    return {"hero": h1, "hero2": h2, "faction": f1, "faction2": f2, "boss": _rng.choice(BOSSES), "place": _rng.choice(PLACES),
            "food": _rng.choice(FOODS), "num": _rng.randint(2, 7), "big": _rng.randint(2, 40) * 100, "lvl": _rng.randint(15, 60),
            "event": ev.name if ev else "Вторжение Тьмы"}


def _cast(personas: list[AiPersona], script: dict) -> dict[str, AiPersona] | None:
    roles = ["A", "B", "C"][: script["roles"]]
    pool = list(personas)
    _rng.shuffle(pool)
    out: dict[str, AiPersona] = {}
    for r in roles:
        pref = script.get("pref", {}).get(r, [])
        pick = next((p for p in pool if p.style in pref), None) or (pool[0] if pool else None)
        if pick is None:
            return None
        out[r] = pick
        pool.remove(pick)
    return out


def start_conversation(db: Session, channel: str = "global", candidates: list[AiPersona] | None = None) -> int:
    personas = candidates or db.scalars(select(AiPersona).where(AiPersona.active.is_(True)).limit(120)).all()
    if len(personas) < 2:
        return 0
    from .population import _awake
    awake = [p for p in personas if _awake(p)]
    others = [p for p in personas if p not in awake]
    _rng.shuffle(others)
    # a mix: whoever is "online" by schedule plus a few others, so it is not always the same three voices
    personas = awake + others[: max(4, 8 - len(awake))]
    script = _rng.choices(SCRIPTS, weights=[s["w"] for s in SCRIPTS])[0]
    cast = _cast(personas, script)
    if cast is None:
        return 0
    names = {r: db.get(PlayerProfile, p.user_id).nickname for r, p in cast.items()}
    ctx = _ctx(db)
    due = time.monotonic() + _rng.uniform(1, 8)
    n = 0
    for role, variants in script["turns"]:
        if role not in cast:
            continue
        text = _fill(_rng.choice(variants), names, ctx)
        _queue.append((due, cast[role].user_id, channel, text))
        due += _rng.uniform(12, 55)  # typing pauses, like people
        n += 1
    return n


def ambient(db: Session, persona: AiPersona, channel: str = "global") -> str:
    pool = AMBIENT.get(persona.style, []) + AMBIENT["any"]
    text = _fill(_rng.choice(pool), {}, _ctx(db))
    _queue.append((time.monotonic() + _rng.uniform(0, 5), persona.user_id, channel, text))
    return text


def flush(db: Session, limit: int = 20) -> int:
    """Posts queued lines whose time has come."""
    now = time.monotonic()
    posted = 0
    keep = deque()
    while _queue:
        item = _queue.popleft()
        if item[0] > now or posted >= limit:
            keep.append(item)
            continue
        _, uid, channel, text = item
        if db.get(PlayerProfile, uid) is None:
            continue
        db.add(ChatMessage(channel=channel, user_id=uid, text=text[:300], is_ai=True, reactions={}))
        p = db.get(PlayerProfile, uid)
        p.last_seen_at = utcnow()
        posted += 1
    _queue.extend(keep)
    db.flush()
    return posted


def ai_messages_last_hour(db: Session, channel: str = "global") -> int:
    from datetime import timedelta
    since = utcnow() - timedelta(hours=1)
    return db.scalar(select(func.count()).select_from(ChatMessage).where(
        ChatMessage.channel == channel, ChatMessage.is_ai.is_(True), ChatMessage.created_at >= since)) or 0


def minutes_since_last(db: Session, channel: str = "global") -> float:
    last = db.scalar(select(func.max(ChatMessage.created_at)).where(ChatMessage.channel == channel))
    if last is None:
        return 1e9
    from ...core.db import as_utc
    return (utcnow() - as_utc(last)).total_seconds() / 60


def keep_alive(db: Session, cfg: dict) -> dict:
    """Keeps the global chat (and AI-guild chats with real members) alive within the hourly cap."""
    global _last_start
    from .control import global_switches
    if not global_switches(db).get("chat", True):
        _queue.clear()
        return {"posted": 0, "started": 0, "disabled": True}
    stats = {"posted": flush(db), "started": 0}
    pending = len(_queue)
    if pending == 0 and ai_messages_last_hour(db) < cfg.get("chat_ai_per_hour", 45):
        quiet = minutes_since_last(db) >= cfg.get("quiet_minutes", 3)
        since_start = time.monotonic() - _last_start
        if quiet or since_start > cfg.get("conversation_every_s", 200) or _rng.random() < 0.2:
            if _rng.random() < 0.8:
                stats["started"] = start_conversation(db)
            else:
                p = db.scalars(select(AiPersona).where(AiPersona.active.is_(True)).order_by(func.random()).limit(1)).first()
                if p:
                    ambient(db, p)
                    stats["started"] = 1
            _last_start = time.monotonic()
    # guild chats: only guilds where real players can read; at most one conversation in progress overall
    if pending == 0 and _rng.random() < cfg.get("guild_chat_chance", 0.25):
        from ...models import Guild
        humans = db.execute(select(GuildMember.guild_id).join(PlayerProfile, PlayerProfile.user_id == GuildMember.user_id)
                            .where(PlayerProfile.is_ai.is_(False))).scalars().all()
        for gid in set(humans):
            g = db.get(Guild, gid)
            if g is None or minutes_since_last(db, f"guild:{gid}") < cfg.get("guild_quiet_minutes", 20):
                continue
            ids = [m.user_id for m in db.scalars(select(GuildMember).where(GuildMember.guild_id == gid))]
            members = db.scalars(select(AiPersona).where(AiPersona.user_id.in_(ids), AiPersona.active.is_(True))).all()
            if len(members) >= 2:
                stats["started"] += start_conversation(db, f"guild:{gid}", list(members))
                break
    return stats


def react_sometimes(db: Session) -> int:
    """Personas react to recent messages (incl. real players') — a little life without spamming."""
    from datetime import timedelta
    if _rng.random() > 0.35:
        return 0
    since = utcnow() - timedelta(minutes=15)
    msgs = db.scalars(select(ChatMessage).where(ChatMessage.channel == "global", ChatMessage.created_at >= since,
                                                ChatMessage.user_id.is_not(None), ChatMessage.hidden.is_(False))
                      .order_by(ChatMessage.id.desc()).limit(15)).all()
    if not msgs:
        return 0
    m = _rng.choice(msgs)
    p = db.scalars(select(AiPersona).where(AiPersona.active.is_(True), AiPersona.user_id != m.user_id)
                   .order_by(func.random()).limit(1)).first()
    if p is None:
        return 0
    emo = "😂" if any(x in m.text for x in ("😂", "ахах", "лол", "🤡")) else _rng.choice(["👍", "🔥", "😂", "❤️", "⚔️"])
    r = {k: list(v) for k, v in (m.reactions or {}).items()}
    lst = r.setdefault(emo, [])
    if p.user_id not in lst:
        lst.append(p.user_id)
        m.reactions = r
        return 1
    return 0
