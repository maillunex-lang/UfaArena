"""Static MVP content (seeded into the DB, later delivered as balance/content packages).

ДИЗАЙН-ПОМЕТКИ. Буквенные решения ранних этапов (фракции «структура C», классы «D»,
формация «C», дубликаты «D» и т.д.) не имеют исходных формулировок в комплекте
документов. Значения ниже — ВРЕМЕННЫЕ (provisional) для вертикального среза и
помечены в docs/GDD_OPEN_QUESTIONS.md как требующие уточнения.
"""

RARITIES = {
    1: "Обычный",
    2: "Необычный",
    3: "Редкий",
    4: "Эпический",
    5: "Легендарный",
    6: "Мифический",
}
RARITY_MULT = {1: 1.0, 2: 1.12, 3: 1.25, 4: 1.42, 5: 1.62, 6: 1.85}

# Factions & classes come from the roster (docs/design/URALIA_HERO_FORGE_12_Heroes.md).
# The enemy faction «Порождения Шульгана» stays as a non-playable faction for campaign foes.
from . import roster as _R

FACTIONS = [dict(f, is_rare=False) for f in _R.factions()] + [
    dict(code="shulgan", name="Порождения Шульгана", strong_against=None, is_rare=False, emblem="shulgan",
         color="#8a5bd6", description="Тени подземного мира, пробудившиеся после Раскола. Только противники."),
]
CLASSES = [dict(code=c["code"], name=c["name"], role=c["role"]) for c in _R.classes()]

# skill.kind: strike | aoe | heal | shield | stun ; power = multiplier of ATK
HEROES = [
    # --- playable
    dict(code="ilgiz", name="Ильгиз", title="Ополченец заставы", faction_code="uraltau", class_code="guardian",
         rarity=1, base_hp=980, base_atk=62, base_def=48, base_spd=88, model="knight",
         skill=dict(kind="shield", name="Каменный заслон", power=1.2, desc="Щит союзнику с наименьшим здоровьем."),
         lore="Сын кузнеца из Стерлитамака, первым встал у ворот крепости."),
    dict(code="mirgali", name="Миргали", title="Лесоруб Ашкадара", faction_code="agidel", class_code="warrior",
         rarity=1, base_hp=820, base_atk=86, base_def=30, base_spd=96, model="barbarian",
         skill=dict(kind="strike", name="Удар топора", power=1.9, desc="Мощный удар по ближайшему врагу."),
         lore="Рубит сухостой в борах у Ашкадара и сухие корни Шульгана."),
    dict(code="gulnaz", name="Гульназ", title="Травница Агидели", faction_code="agidel", class_code="healer",
         rarity=2, base_hp=700, base_atk=58, base_def=26, base_spd=104, model="mage",
         skill=dict(kind="heal", name="Отвар чабреца", power=1.6, desc="Лечит союзника с наименьшим здоровьем."),
         lore="Собирает травы на склонах шиханов и помнит песни бабушки."),
    dict(code="ramil", name="Рамиль", title="Дозорный степи", faction_code="steppe", class_code="ranger",
         rarity=2, base_hp=690, base_atk=94, base_def=24, base_spd=112, model="rogue",
         skill=dict(kind="strike", name="Меткий болт", power=2.0, desc="Выстрел по врагу с наименьшим здоровьем."),
         lore="Видит дым костра за десять вёрст."),
    dict(code="azamat", name="Азамат", title="Щит Юрактау", faction_code="uraltau", class_code="guardian",
         rarity=3, base_hp=1250, base_atk=70, base_def=62, base_spd=90, model="knight",
         skill=dict(kind="stun", name="Гнев горы", power=1.3, desc="Оглушает ближайшего врага на 1 ход."),
         lore="Дал клятву хранить шиханы, пока стоит Урал-тау."),
    dict(code="zulfiya", name="Зульфия", title="Стрела ветра", faction_code="steppe", class_code="ranger",
         rarity=3, base_hp=760, base_atk=112, base_def=28, base_spd=118, model="rogue",
         skill=dict(kind="aoe", name="Ливень стрел", power=1.0, desc="Залп по всем врагам."),
         lore="Её стрелы поют, как курай на ветру."),
    dict(code="burebai", name="Буребай", title="Батыр Иремеля", faction_code="uraltau", class_code="warrior",
         rarity=4, base_hp=1100, base_atk=128, base_def=40, base_spd=100, model="barbarian",
         skill=dict(kind="aoe", name="Сотрясение земли", power=1.25, desc="Удар по всем врагам."),
         lore="Спустился с Иремеля, когда горы загудели от Раскола."),
    dict(code="tansulpan", name="Тансулпан", title="Тень рассвета", faction_code="steppe", class_code="ranger",
         rarity=4, base_hp=820, base_atk=140, base_def=30, base_spd=130, model="rogue_hooded",
         skill=dict(kind="strike", name="Клинок зари", power=2.6, desc="Удар по самому слабому врагу."),
         lore="Её имя означает «утренняя звезда». Никто не видел её лица."),
    dict(code="aigul", name="Айгуль", title="Голос Агидели", faction_code="agidel", class_code="mage",
         rarity=5, base_hp=880, base_atk=150, base_def=32, base_spd=110, model="mage",
         skill=dict(kind="aoe", name="Половодье", power=1.45, desc="Волна, поражающая всех врагов."),
         lore="Говорят, река отвечает ей, когда она поёт."),
    dict(code="humai", name="Хумай", title="Дева-птица", faction_code="ancients", class_code="healer",
         rarity=6, base_hp=1000, base_atk=130, base_def=40, base_spd=120, model="mage_gold",
         skill=dict(kind="heal", name="Крыло рассвета", power=2.2, desc="Сильное исцеление и щит союзнику."),
         lore="Образ из эпоса: дух-покровительница, вернувшаяся к людям в час беды."),
    # --- enemies (Порождения Шульгана)
    dict(code="e_minion", name="Костяной прислужник", faction_code="shulgan", class_code="warrior", rarity=1,
         base_hp=520, base_atk=58, base_def=18, base_spd=90, model="skeleton_minion", is_enemy=True, summonable=False,
         skill=dict(kind="strike", name="Укус", power=1.5, desc="")),
    dict(code="e_warrior", name="Курганный воин", faction_code="shulgan", class_code="guardian", rarity=2,
         base_hp=860, base_atk=64, base_def=40, base_spd=84, model="skeleton_warrior", is_enemy=True, summonable=False,
         skill=dict(kind="shield", name="Ржавый щит", power=1.0, desc="")),
    dict(code="e_rogue", name="Пещерный ловчий", faction_code="shulgan", class_code="ranger", rarity=2,
         base_hp=600, base_atk=82, base_def=20, base_spd=110, model="skeleton_rogue", is_enemy=True, summonable=False,
         skill=dict(kind="strike", name="Подлый выстрел", power=1.8, desc="")),
    dict(code="e_mage", name="Шаман подземья", faction_code="shulgan", class_code="mage", rarity=3,
         base_hp=640, base_atk=90, base_def=22, base_spd=100, model="skeleton_mage", is_enemy=True, summonable=False,
         skill=dict(kind="aoe", name="Чёрный туман", power=0.9, desc="")),
    dict(code="e_boss_toratau", name="Страж Кургана", title="Узник Торатау", faction_code="shulgan",
         class_code="guardian", rarity=5, base_hp=2400, base_atk=105, base_def=50, base_spd=86,
         model="skeleton_boss", is_enemy=True, summonable=False,
         skill=dict(kind="aoe", name="Обвал", power=1.2, desc="")),
]

# Legacy heroes of the 0.1 slice keep their codes (players own them) but move into official factions.
for _h in HEROES:
    _h["faction_code"] = _R.map_faction(_h["faction_code"])
    if _h["code"] in _R.roster().get("enemy_kits", {}):
        _h["kit"] = _R.roster()["enemy_kits"][_h["code"]]
HEROES += _R.new_heroes()

# New players start with a tank from the slice plus three heroes of the official roster.
STARTER_HEROES = ["azamat", "yurek", "safariy", "tan_chechek"]
ONBOARDING_SUMMON_HERO = "ai_tulgan"  # guaranteed first summon in onboarding (Редкий, Поддержка)

# Region 1. Real places: шиханы Торатау, Юрактау, Куштау, Шахтау (Ишимбайский /
# Стерлитамакский р-ны), реки Белая (Агидель) и Ашкадар, г. Стерлитамак.
# Фэнтезийная интерпретация мест — гибридная структура кампании.
REGIONS = [
    dict(code="r1_shikhany", order=1, name="Шиханы Приагиделья",
         real_place="Стерлитамакский и Ишимбайский районы, Республика Башкортостан",
         description="Четыре одиноких горы-шихана над долиной Агидели. После Раскола "
                     "из-под Торатау потянулись тени Шульгана."),
]


def _e(code, level, slot):
    return dict(hero_code=code, level=level, slot=slot)


NODES = [
    dict(code="1-1", order=1, name="Берег Агидели", territory="nature", real_place="р. Белая (Агидель)",
         map_pos=[0, 0], enemies=[_e("e_minion", 1, 0), _e("e_minion", 1, 1)],
         rewards=dict(gold=120), first_clear_rewards=dict(crystals=50, summon_essence=1),
         story=[dict(speaker="yurek", text="Следы ведут из ила… Это не звери. Кости поднимаются со дна Агидели!"),
                dict(speaker="azamat", text="Держитесь за мной. Крепость не падёт в первый же день.")]),
    dict(code="1-2", order=2, name="Бор у Ашкадара", territory="nature", real_place="р. Ашкадар",
         map_pos=[1, 0], enemies=[_e("e_minion", 2, 0), _e("e_rogue", 2, 2), _e("e_minion", 2, 1)],
         rewards=dict(gold=150), first_clear_rewards=dict(crystals=50, nature_essence=30),
         story=[dict(speaker="yurek", text="В этом бору я знаю каждую тропу. Чужих следов нет — только мертвецы. И это хуже.")]),
    dict(code="1-3", order=3, name="Застава Стерлитамака", territory="settlements", real_place="г. Стерлитамак",
         map_pos=[2, -1], enemies=[_e("e_warrior", 4, 0), _e("e_minion", 4, 1), _e("e_rogue", 4, 2), _e("e_minion", 4, 3)],
         rewards=dict(gold=180), first_clear_rewards=dict(crystals=60, summon_essence=1),
         story=[dict(speaker="azamat", text="Застава держится. Люди уходят под защиту Крепости хранителей.")]),
    dict(code="1-4", order=4, name="Склоны Юрактау", territory="nature", real_place="шихан Юрактау",
         map_pos=[3, -1], enemies=[_e("e_warrior", 6, 0), _e("e_minion", 6, 1), _e("e_mage", 6, 2), _e("e_rogue", 6, 3)],
         rewards=dict(gold=210), first_clear_rewards=dict(crystals=60, nature_essence=40),
         story=[dict(speaker="tan_chechek", text="Чабрец на Юрактау ещё цветёт. Значит, увядание сюда не дошло. Пока.")]),
    dict(code="1-5", order=5, name="Каменные залы Куштау", territory="dungeons", real_place="шихан Куштау",
         map_pos=[3, 0], enemies=[_e("e_warrior", 8, 0), _e("e_warrior", 8, 1), _e("e_mage", 8, 2), _e("e_rogue", 8, 3)],
         rewards=dict(gold=240), first_clear_rewards=dict(crystals=80, summon_essence=2),
         story=[dict(speaker="safariy", text="Руны на стенах Куштау сбились с ритма. Кто-то переписал их чужим языком."),
                dict(speaker="safariy", text="Не трогайте знаки. Знание — это ответственность, а не любопытство.")]),
    dict(code="1-6", order=6, name="Разлом Шахтау", territory="resources", real_place="шихан Шахтау (карьер)",
         map_pos=[4, 0], enemies=[_e("e_warrior", 10, 0), _e("e_minion", 10, 1), _e("e_rogue", 10, 2), _e("e_mage", 10, 3), _e("e_rogue", 10, 4)],
         rewards=dict(gold=270), first_clear_rewards=dict(crystals=80, ancient_seals=1),
         story=[dict(speaker="zarkhan", text="Разлом свежий. Тот, кто его открыл, ушёл к Торатау. Никто не исчезает бесследно.")]),
    dict(code="1-7", order=7, name="Тропа на Торатау", territory="complexes", real_place="шихан Торатау",
         map_pos=[5, -1], enemies=[_e("e_warrior", 13, 0), _e("e_warrior", 13, 1), _e("e_rogue", 13, 2), _e("e_mage", 13, 3), _e("e_mage", 13, 4)],
         rewards=dict(gold=300), first_clear_rewards=dict(crystals=100, summon_essence=2),
         story=[dict(speaker="ai_tulgan", text="Я слышу голоса в ветре над Торатау. Они просят пройти. Значит, пройдём.")]),
    dict(code="1-8", order=8, name="Вершина Торатау", territory="dimensions", real_place="шихан Торатау",
         map_pos=[6, -1], is_boss=True,
         enemies=[_e("e_boss_toratau", 19, 0), _e("e_warrior", 15, 1), _e("e_mage", 15, 3), _e("e_rogue", 15, 4)],
         rewards=dict(gold=400), first_clear_rewards=dict(crystals=300, summon_essence=5, ancient_seals=2),
         story=[dict(speaker="azamat", text="Страж Кургана! Он стерёг проход в подземье с начала времён."),
                dict(speaker="ai_tulgan", text="Держитесь вместе. Если мы победим, Агидель снова станет светлой.")]),
]

# ---------------------------------------------------------------- chapters 2-7 (temporary extension)
# 60 extra stages so testers have room to progress. Real places of Bashkortostan; stage content is
# procedurally laid out and will be replaced by hand-made chapters (see roadmap).
EXTRA_CHAPTERS = [
    ("r2_iremel", "Склоны Иремеля", "хребет Иремель, Учалинский и Белорецкий районы",
     ["Подножие Иремеля", "Курумник", "Каменные реки", "Таганайский перевал", "Ущелье ветров", "Плато Иремеля",
      "Ледяной ручей", "Старый скит", "Туман вершины", "Вершина Иремеля"]),
    ("r3_shulgantash", "Пещера Шульган-Таш", "Капова пещера, Бурзянский район",
     ["Вход в Шульган-Таш", "Зал Знаков", "Голубое озеро", "Купольный зал", "Галерея рисунков", "Подземная река",
      "Зал Хаоса", "Бриллиантовый зал", "Сердце пещеры", "Трон Шульгана"]),
    ("r4_nugush", "Долина Нугуша", "р. Нугуш и Нугушское водохранилище, Мелеузовский район",
     ["Берег Нугуша", "Бортевые леса", "Водохранилище", "Утёс Кузгун", "Брод у Ташасты", "Медовые поляны",
      "Скала Ташбаш", "Затопленная деревня", "Плотина", "Омут Нугуша"]),
    ("r5_yangantau", "Горящая гора Янгантау", "гора Янгантау, Салаватский район",
     ["Дорога на Янгантау", "Тёплые камни", "Курортная тропа", "Дымящиеся трещины", "Пещера жара",
      "Огненный склон", "Источник Кургазак", "Обугленный лес", "Жерло горы", "Сердце огня"]),
    ("r6_ufa_plateau", "Уфимское плато", "Уфимское плато, Караидельский район",
     ["Край плато", "Карстовые воронки", "Павловское водохранилище", "Лесная дорога", "Красный ключ",
      "Скалы Уфы", "Сплавная река", "Охотничья заимка", "Обрыв плато", "Ворота разлома"]),
    ("r7_zilair", "Зилаирское плато", "Зилаирское плато, Зилаирский и Баймакский районы",
     ["Степной подъём", "Ковыльное море", "Курганы", "Стоянка кочевников", "Перевал Ирендык",
      "Солёное озеро", "Каменная баба", "Пепельная степь", "Предел разлома", "Сердце Предела"]),
]
_TERR = ["nature", "settlements", "dungeons", "nature", "complexes", "resources", "nature", "dungeons", "dimensions", "dimensions"]
_SQUADS = [
    ["e_minion", "e_warrior", "e_rogue"], ["e_warrior", "e_minion", "e_rogue", "e_mage"],
    ["e_warrior", "e_warrior", "e_mage", "e_rogue"], ["e_warrior", "e_minion", "e_rogue", "e_mage", "e_rogue"],
    ["e_warrior", "e_warrior", "e_rogue", "e_mage", "e_mage"],
]
_SLOTS = {"e_warrior": [0, 1], "e_minion": [1, 0], "e_rogue": [2, 4, 3], "e_mage": [3, 4, 2]}

for _ci, (_rc, _rn, _place, _names) in enumerate(EXTRA_CHAPTERS):
    REGIONS.append(dict(code=_rc, order=_ci + 2, name=_rn, real_place=_place + ", Республика Башкортостан",
                        description="Временная глава для тестирования прогрессии."))
    for _k, _nm in enumerate(_names):
        _idx = _ci * 10 + _k + 1          # 1..60 after chapter 1
        _lvl = int(15 + _idx * 0.85)      # enemy level 15 -> 66
        _boss = _k == 9
        if _boss:
            _en = [_e("e_boss_toratau", _lvl + 4, 0), _e("e_warrior", _lvl, 1), _e("e_mage", _lvl, 3), _e("e_rogue", _lvl, 4)]
        else:
            _used, _en = set(), []
            for _h in _SQUADS[min(4, _k // 2 + _ci // 3)]:
                _slot = next(s for s in _SLOTS[_h] if s not in _used)
                _used.add(_slot)
                _en.append(_e(_h, _lvl, _slot))
        _first = dict(crystals=60 + 2 * _idx)
        if _k % 5 == 4:
            _first["summon_essence"] = 1 + _ci // 2
        if _boss:
            _first.update(crystals=300 + 20 * _ci, summon_essence=3 + _ci, ancient_seals=2)
        NODES.append(dict(code=f"{_ci + 2}-{_k + 1}", region_code=_rc, order=_k + 1, name=_nm, territory=_TERR[_k],
                          real_place=_place.split(",")[0], map_pos=[_k, -((_k // 2) % 2)], is_boss=_boss,
                          enemies=_en, rewards=dict(gold=400 + 25 * _idx), first_clear_rewards=_first,
                          story=[dict(speaker="narrator", text=f"Глава {_ci + 2}: {_rn}. Тени Шульгана уходят всё дальше — "
                                      "хранители идут следом.")] if _k == 0 else []))

SUMMON_POOLS = [
    dict(code="standard", name="Зов предков",
         rates={"1": 0.40, "2": 0.30, "3": 0.18, "4": 0.09, "5": 0.027, "6": 0.003},
         cost={"summon_essence": 1}, pity_threshold=60, pity_min_rarity=5),
    dict(code="standard_crystals", name="Зов предков (кристаллы)",
         rates={"1": 0.40, "2": 0.30, "3": 0.18, "4": 0.09, "5": 0.027, "6": 0.003},
         cost={"crystals": 300}, pity_threshold=60, pity_min_rarity=5),
]

# provisional duplicate rule ("дубликаты D" — требует уточнения): дубликат даёт осколки,
# 10 осколков = +1 звезда (макс. 5), каждая звезда +8% к характеристикам.
DUP_SHARDS = {1: 2, 2: 3, 3: 5, 4: 8, 5: 10, 6: 10}
SHARDS_PER_STAR = 10
MAX_STARS = 5
STAR_MULT = 0.08

LEVEL_CAP_MVP = 80  # raised with the temporary chapters 2-7


def level_up_cost(level: int) -> dict:
    return {"gold": 40 * level + 5 * level * level, "nature_essence": 2 + level}


BUILDINGS = {
    "summon_hall": dict(name="Зал призыва", max_level=10, effect="Эссенция призыва из AFK: +1 за каждые 8/уровень ч."),
    "forge": dict(name="Кузница", max_level=10, effect="+3% атаки всем героям за уровень."),
    "training": dict(name="Тренировочный двор", max_level=10, effect="+3% здоровья всем героям за уровень."),
    "alchemy": dict(name="Алхимическая башня", max_level=10, effect="+10% эссенции природы в AFK за уровень."),
    "storage": dict(name="Хранилище", max_level=10, effect="Лимит AFK: 8 ч + 1 ч за уровень сверх первого."),
    "guild_house": dict(name="Дом гильдий", max_level=1, effect="Откроется вместе с гильдиями (следующий блок).",
                        locked=True),
}


def building_upgrade_cost(code: str, level: int) -> dict:
    return {"gold": 400 * level * level, "nature_essence": 20 * level}


QUESTS = [
    dict(code="main_first_battle", kind="main", order=1, title="Первая кровь у Агидели",
         description="Пройди бой «Берег Агидели».", event="campaign_clear", target=1,
         rewards=dict(gold=300, crystals=100)),
    dict(code="main_first_summon", kind="main", order=2, title="Зов предков",
         description="Призови героя в Зале призыва.", event="summon", target=1,
         rewards=dict(summon_essence=1), requires="main_first_battle"),
    dict(code="main_afk", kind="main", order=3, title="Плоды дозора",
         description="Забери AFK-награды.", event="afk_claim", target=1,
         rewards=dict(gold=500), requires="main_first_summon"),
    dict(code="main_level_up", kind="main", order=4, title="Сила растёт",
         description="Повысь уровень любого героя 3 раза.", event="hero_level_up", target=3,
         rewards=dict(nature_essence=60), requires="main_afk"),
    dict(code="main_fortress", kind="main", order=5, title="Стены крепости",
         description="Улучши любое здание крепости.", event="building_upgrade", target=1,
         rewards=dict(crystals=150), requires="main_level_up"),
    dict(code="main_region1", kind="main", order=6, title="Освобождение Торатау",
         description="Пройди всю главу «Шиханы Приагиделья».", event="campaign_clear", target=8,
         rewards=dict(crystals=500, ancient_seals=2), requires="main_fortress"),
    dict(code="daily_battles", kind="daily", order=10, title="Ежедневный дозор",
         description="Проведи 3 боя.", event="battle_fought", target=3, rewards=dict(gold=400, crystals=30)),
    dict(code="daily_afk", kind="daily", order=11, title="Сбор дани",
         description="Забери AFK-награды 2 раза.", event="afk_claim", target=2, rewards=dict(nature_essence=30)),
    dict(code="side_collector", kind="side", order=20, title="Собиратель легенд",
         description="Собери 6 разных героев.", event="hero_collected", target=6,
         rewards=dict(summon_essence=3)),
]

WELCOME_MAIL = dict(code="welcome_v1", title="Добро пожаловать в Уралию!",
                    body="Хранитель! Крепость приветствует тебя. Прими дары предков для первого призыва.",
                    attachments=dict(summon_essence=5, crystals=300, gold=1000))

# Battle speed-up by VIP level (convenience only, never power — GDD: no Pay-to-Win).
# provisional thresholds; VIP sources (cosmetic VIP / Battle Pass) arrive with the monetization block.
VIP_BATTLE_SPEEDS = [(0, [1, 2]), (1, [1, 2, 4]), (3, [1, 2, 4, 6])]


def battle_speeds(vip_level: int) -> list[int]:
    allowed = [1, 2]
    for lvl, speeds in VIP_BATTLE_SPEEDS:
        if vip_level >= lvl:
            allowed = speeds
    return allowed


STARTING_WALLET = dict(gold=2000, crystals=200, summon_essence=1, ancient_seals=0, guild_marks=0, nature_essence=100)
