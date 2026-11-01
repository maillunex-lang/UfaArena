"""Persona registry data: varied names, archetypes, styles, schedules and backstories.
Combined randomly so the population does not look like copies of one template."""
from __future__ import annotations

import random

NAMES_M = ["Айбулат", "Азат", "Ильдар", "Тимур", "Рустем", "Салават", "Ринат", "Булат", "Марсель", "Артур", "Динар",
           "Ильнур", "Егор", "Максим", "Олег", "Денис", "Камиль", "Радик", "Ильшат", "Арслан", "Самат", "Глеб", "Яромир"]
NAMES_F = ["Айгуль", "Зарина", "Гульнара", "Алсу", "Лейсан", "Регина", "Диляра", "Юлия", "Ксения", "Эльвира", "Миляуша",
           "Назгуль", "Камила", "Аделина", "Ралина", "Вера", "Таисия", "Зиля", "Айсылу", "Динара"]
EPITHETS = ["Курай", "Урал", "Беркут", "Тулпар", "Шихан", "Агидель", "Ирендык", "Торатау", "Иремель", "Буран", "Сокол",
            "Волк", "Лис", "Камень", "Ветер", "Ночь", "Рассвет", "Клинок", "Щит", "Тень", "Туман", "Лучник", "Странник"]
ADJ = ["Тихий", "Хмурый", "Весёлый", "Седой", "Быстрый", "Лесной", "Горный", "Северный", "Хитрый", "Ленивый", "Бравый",
       "Мудрый", "Дерзкий", "Сонный", "Стальной", "Медовый"]
LATIN = ["batyr", "ural_fox", "kurai", "agidel", "steppe", "wolfie", "shikhan", "berkut", "nomad", "irendyk", "tulpar", "ashka"]

ARCHETYPES = {
    "competitor": {"interests": ["arena", "chat", "level"], "styles": ["competitive", "grumpy", "joker", "bro"],
                   "lvl": (18, 45), "desc": "Любит арену и рейтинги"},
    "collector": {"interests": ["level", "chat", "raid"], "styles": ["friendly", "joker", "bro", "grumpy"],
                  "lvl": (12, 40), "desc": "Собирает героев и считает шансы призыва"},
    "socializer": {"interests": ["chat", "friend", "guild"], "styles": ["joker", "friendly", "shy", "bro", "flirty"],
                   "lvl": (8, 30), "desc": "Ради общения и гильдии"},
    "strategist": {"interests": ["raid", "level", "arena"], "styles": ["wise", "grumpy", "laconic", "bro"],
                   "lvl": (20, 50), "desc": "Разбирает синергии фракций"},
    "explorer": {"interests": ["level", "chat", "event"], "styles": ["friendly", "wise", "shy", "flirty"],
                 "lvl": (10, 35), "desc": "Изучает регионы и сюжет"},
    "newbie": {"interests": ["level", "chat", "friend"], "styles": ["shy", "friendly", "joker"],
               "lvl": (3, 12), "desc": "Только начал путь"},
    "veteran": {"interests": ["guild", "raid", "arena", "chat"], "styles": ["wise", "grumpy", "competitive", "bro"],
                "lvl": (35, 60), "desc": "Опора своей гильдии"},
}

BACKSTORIES = [
    "Пришёл в Уралию из степей Зауралья, ищет следы предков у Иремеля.",
    "Говорит, что дед рассказывал ему сказку об Урал-батыре каждый вечер.",
    "Собирает легенды о шиханах и записывает их в свой дневник.",
    "Бывший лучник дозора Стерлитамака, теперь странствует с отрядом.",
    "Мечтает собрать всех героев Живого Курая.",
    "Хранитель из горного аула, верит, что камни Торатау помнят всё.",
    "Любит рассвет над Агиделью и не любит проигрывать на арене.",
    "Ищет друзей для совместной охоты на Аждаху.",
    "Тихо помогает новичкам и редко рассказывает о себе.",
    "Шутит, что его отряд держится на одном лекаре и молитвах.",
]

AVATARS = ["stone", "kurai", "ash", "wolf", "eagle", "horse", "moon", "sun", "tree", "mountain"]
FRAMES = [None, None, "frame_birch", "frame_kurai", "frame_toratau"]


def nickname(rng: random.Random) -> tuple[str, str]:
    sex = rng.choice("mf")
    name = rng.choice(NAMES_M if sex == "m" else NAMES_F)
    pattern = rng.randrange(7)
    if pattern == 0:
        nick = name
    elif pattern == 1:
        nick = f"{name}_{rng.choice(EPITHETS)}"
    elif pattern == 2:
        nick = f"{rng.choice(ADJ)}{rng.choice(EPITHETS)}"
    elif pattern == 3:
        nick = f"{rng.choice(LATIN)}{rng.randrange(7, 99)}"
    elif pattern == 4:
        nick = f"{name}{rng.randrange(80, 2010)}"
    elif pattern == 5:
        nick = f"{rng.choice(EPITHETS)}{rng.choice(['ов', 'ин', '_x', 'ка', ''])}"
    else:
        nick = f"{name[:4]}{rng.choice(EPITHETS).lower()}"
    return nick[:24], sex


def schedule(rng: random.Random) -> dict:
    """Active hours in UTC (players are mostly UTC+3..+5): morning, evening, night owl or day shift."""
    kind = rng.choice(["evening", "evening", "morning", "owl", "day", "weekend"])
    base = {"evening": range(14, 21), "morning": range(2, 7), "owl": list(range(18, 24)) + [0, 1],
            "day": range(6, 14), "weekend": range(6, 20)}[kind]
    hours = sorted(set(list(base)))
    return {"kind": kind, "hours": hours, "weekend_only": kind == "weekend"}


def make(rng: random.Random) -> dict:
    arch = rng.choice(list(ARCHETYPES))
    a = ARCHETYPES[arch]
    nick, sex = nickname(rng)
    temperament = {"talkative": round(rng.uniform(0.2, 1.0), 2), "helpful": round(rng.uniform(0.3, 1.0), 2),
                   "competitive": round(rng.uniform(0.1, 1.0), 2), "sex": sex}
    return {"nickname": nick, "archetype": arch, "style": rng.choice(a["styles"]), "interests": list(a["interests"]),
            "level": rng.randint(*a["lvl"]), "schedule": schedule(rng), "temperament": temperament,
            "backstory": rng.choice(BACKSTORIES), "avatar": rng.choice(AVATARS), "frame": rng.choice(FRAMES)}
