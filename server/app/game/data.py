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
# The enemy faction «Порождения Глубины» (code "shulgan" kept for saved data) stays as a non-playable faction for campaign foes.
from . import roster as _R

FACTIONS = [dict(f, is_rare=False) for f in _R.factions()] + [
    dict(code="shulgan", name="Порождения Глубины", strong_against=None, is_rare=False, emblem="shulgan",
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
         lore="Рубит сухостой в приречных борах и сухие корни, проросшие из Глубины."),
    dict(code="gulnaz", name="Гульназ", title="Травница переправы", faction_code="agidel", class_code="healer",
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
    dict(code="aigul", name="Айгуль", title="Голос реки", faction_code="agidel", class_code="mage",
         rarity=5, base_hp=880, base_atk=150, base_def=32, base_spd=110, model="mage",
         skill=dict(kind="aoe", name="Половодье", power=1.45, desc="Волна, поражающая всех врагов."),
         lore="Говорят, река отвечает ей, когда она поёт."),
    dict(code="humai", name="Хумай", title="Дева-птица", faction_code="ancients", class_code="healer",
         rarity=6, base_hp=1000, base_atk=130, base_def=40, base_spd=120, model="mage_gold",
         skill=dict(kind="heal", name="Крыло рассвета", power=2.2, desc="Сильное исцеление и щит союзнику."),
         lore="Образ из эпоса: дух-покровительница, вернувшаяся к людям в час беды."),
    # --- enemies (Порождения Глубины)
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
    dict(code="e_boss_toratau", name="Страж Кургана", title="Страж прохода в Глубь", faction_code="shulgan",
         class_code="guardian", rarity=5, base_hp=2400, base_atk=105, base_def=50, base_spd=86,
         model="skeleton_boss", is_enemy=True, summonable=False,
         skill=dict(kind="aoe", name="Обвал", power=1.2, desc="")),
]

# --- raid & world bosses (online systems). Huge HP pools come from the raid config, not from base stats.
def _boss_kit(basic, roar, grip, ult, passive_val=0.6, aoe_mult=1.3):
    return {
        "basic": {"name": basic, "desc": "", "effects": [{"type": "damage", "target": "target", "mult": 0.7, "hits": 2}]},
        "skills": [
            {"id": "b_roar", "name": roar, "desc": "", "cooldown": 10, "first": 4, "anim": "skill",
             "effects": [{"type": "debuff", "target": "all_enemies", "stat": "atk", "value": -0.12, "dur": 6},
                         {"type": "damage", "target": "all_enemies", "mult": 0.45}]},
            {"id": "b_grip", "name": grip, "desc": "", "cooldown": 12, "first": 7, "anim": "skill2",
             "effects": [{"type": "damage", "target": "highest_atk_enemy", "mult": 1.8},
                         {"type": "stun", "target": "same", "dur": 1.2}]}],
        "ultimate": {"name": ult, "desc": "", "effects": [{"type": "damage", "target": "all_enemies", "mult": aoe_mult}]},
        "passive": {"name": "Древняя сила", "desc": "", "type": "cc_resist_static", "params": {"value": passive_val}},
        "mechanic": None,
    }


RAID_BOSSES = [
    dict(code="rb_kurgan_colossus", name="Курганный Колосс", title="Страж курганов", faction_code="shulgan",
         class_code="guardian", rarity=6, base_hp=4200, base_atk=120, base_def=70, base_spd=80,
         model="skeleton_boss", is_enemy=True, summonable=False, skill=dict(kind="aoe", name="Обвал", power=1.3, desc=""),
         kit=_boss_kit("Каменный кулак", "Гул земли", "Каменная хватка", "Обвал курганов")),
    dict(code="rb_azhdaha", name="Аждаха Пепельная", title="Многоголовый змей", faction_code="shulgan",
         class_code="mage", rarity=6, base_hp=4800, base_atk=135, base_def=55, base_spd=92,
         model="dragon", is_enemy=True, summonable=False, skill=dict(kind="aoe", name="Пламя", power=1.4, desc=""),
         kit=_boss_kit("Укус", "Пепельный рёв", "Хвост-плеть", "Огненный шквал", 0.65, 1.45)),
    dict(code="rb_ancient_root", name="Древний Корень", title="Отравленное древо", faction_code="shulgan",
         class_code="summoner", rarity=6, base_hp=5200, base_atk=110, base_def=75, base_spd=76,
         model="tree", is_enemy=True, summonable=False, skill=dict(kind="aoe", name="Шипы", power=1.2, desc=""),
         kit=_boss_kit("Хлёст ветви", "Пыльца забвения", "Корни-оковы", "Лес шипов", 0.7, 1.2)),
    dict(code="rb_shulgan_shade", name="Тень Древнего", title="Воля из Глубины", faction_code="shulgan",
         class_code="mage", rarity=6, base_hp=4500, base_atk=140, base_def=60, base_spd=95,
         model="skeleton_mage", is_enemy=True, summonable=False, skill=dict(kind="aoe", name="Тьма", power=1.4, desc=""),
         kit=_boss_kit("Касание тьмы", "Шёпот бездны", "Хватка теней", "Пожиратель света", 0.65, 1.5)),
]
HEROES += RAID_BOSSES

# Legacy heroes of the 0.1 slice keep their codes (players own them) but move into official factions.
for _h in HEROES:
    _h["faction_code"] = _R.map_faction(_h["faction_code"])
    if _h["code"] in _R.roster().get("enemy_kits", {}):
        _h["kit"] = _R.roster()["enemy_kits"][_h["code"]]
HEROES += _R.new_heroes()

# New players start with a tank from the slice plus three heroes of the official roster.
STARTER_HEROES = ["azamat", "yurek", "safariy", "tan_chechek"]
ONBOARDING_SUMMON_HERO = "ai_tulgan"  # guaranteed first summon in onboarding (Редкий, Поддержка)

# Land I «Таулар — край Одиноких Гор» (approved lore, docs/lore). Inspired by the shikhans above the Agidel valley
# (Bashkortostan); names in the game are original (decision D-02). Codes are unchanged, so player progress is kept.
REGIONS = [
    dict(code="r1_shikhany", order=1, name="Таулар",
         real_place="Край Одиноких Гор",
         description="Речная долина, над которой стоят четыре одиноких горы. На вершине главной — первая из семи печатей "
                     "Древнего. В ночь Раскола она разрушилась."),
]


def _e(code, level, slot):
    return dict(hero_code=code, level=level, slot=slot)


NODES = [
    dict(code="1-1", order=1, name="Ночная переправа", territory="nature", real_place="Таулар",
         map_pos=[0, 0], enemies=[_e("e_minion", 1, 0), _e("e_minion", 1, 1)],
         rewards=dict(gold=120), first_clear_rewards=dict(crystals=50, summon_essence=1),
         story=[dict(speaker="narrator", text="Ночь Раскола. Земля гудит, над главной горой бьют белые вспышки."),
                dict(speaker="yurek", text="Это не звери. Кости поднимаются со дна реки — прямо к переправе!"),
                dict(speaker="azamat", text="Стражи Заставы, ко мне! Люди уходят — мы держим берег.")]),
    dict(code="1-2", order=2, name="Сосновый бор", territory="nature", real_place="Таулар",
         map_pos=[1, 0], enemies=[_e("e_minion", 2, 0), _e("e_rogue", 2, 2), _e("e_minion", 2, 1)],
         rewards=dict(gold=150), first_clear_rewards=dict(crystals=50, nature_essence=30),
         story=[dict(speaker="timer", text="Я уведу людей через бор! Догоняй, слышишь? Не геройствуй!"),
                dict(choice="prologue_timer"),
                {"if": {"timer_path": "followed"}, "speaker": "timer", "text": "Ты всё-таки побежал за нами? Спасибо… Тогда держись рядом — мертвецы уже в бору."},
                {"if": {"timer_path": "stayed"}, "speaker": "azamat", "text": "Правильно. Люди с Тимером, а печать — без хранителей. Идём к Заставе."},
                dict(speaker="yurek", text="В этом бору я знаю каждую тропу. Чужих следов нет — только мертвецы. И это хуже.")]),
    dict(code="1-3", order=3, name="Застава у Белой горы", territory="settlements", real_place="Таулар",
         map_pos=[2, -1], enemies=[_e("e_warrior", 4, 0), _e("e_minion", 4, 1), _e("e_rogue", 4, 2), _e("e_minion", 4, 3)],
         rewards=dict(gold=180), first_clear_rewards=dict(crystals=60, summon_essence=1),
         story=[{"if": {"timer_path": "followed"}, "speaker": "timer", "text": "Дальше я сам. Люди в безопасности — возвращайся к Заставе, там ты нужнее. Встретимся… когда-нибудь."},
                {"if": {"timer_path": "stayed"}, "speaker": "narrator", "text": "Где-то в бору остались Тимер и люди. Ты не знаешь, дошли ли они."},
                dict(speaker="kahym", text="Застава не устоит. Печать на вершине трескается — я поднимусь к ней."),
                dict(speaker="azamat", text="Хранитель Кахым, один вы не удержите! Хранитель, за ним — мы прикроем!")]),
    dict(code="1-4", order=4, name="Расколотая печать", territory="dimensions", real_place="Таулар",
         map_pos=[3, -1], enemies=[_e("e_warrior", 6, 0), _e("e_minion", 6, 1), _e("e_mage", 6, 2), _e("e_rogue", 6, 3)],
         rewards=dict(gold=210), first_clear_rewards=dict(crystals=60, nature_essence=40),
         story=[dict(speaker="narrator", text="Вершина. Каменный круг печати раскалывается, и осколок света врезается тебе в ладонь."),
                dict(speaker="kahym", text="Он… выбрал тебя. Береги… Ильсура…"),
                dict(speaker="ancient", text="Наконец-то кто-то услышал. Не бойся. Пока — не бойся."),
                dict(choice="prologue_voice"),
                {"if": {"voice_tone": "answer"}, "speaker": "ancient", "text": "Кто я? Тот, кого заперли. Тот, кто ждал. Мы ещё поговорим — если ты захочешь слушать."},
                {"if": {"voice_tone": "silent"}, "speaker": "ancient", "text": "Молчишь. Разумно. Слушать полезнее, чем спрашивать."},
                {"if": {"voice_tone": "reject"}, "speaker": "ancient", "text": "Убраться? Я в твоей крови, носитель. Но как хочешь — пока помолчу."},
                dict(speaker="ilsur", text="Значит, он выбрал тебя. Я — Ильсур, ученик Кахыма. Объяснять потом. Сейчас — живые.")]),
    dict(code="1-5", order=5, name="Залы сбившихся знаков", territory="dungeons", real_place="Таулар",
         map_pos=[3, 0], enemies=[_e("e_warrior", 8, 0), _e("e_warrior", 8, 1), _e("e_mage", 8, 2), _e("e_rogue", 8, 3)],
         rewards=dict(gold=240), first_clear_rewards=dict(crystals=80, summon_essence=2),
         story=[dict(speaker="safariy", text="Знаки на стенах сбились с ритма. Кто-то переписал их чужим языком."),
                dict(speaker="ilsur", text="Не чужим — древним. И переписали недавно: резец ещё не потемнел."),
                dict(speaker="ancient", text="Видишь? Кто-то очень ждал этой ночи.")]),
    dict(code="1-6", order=6, name="Разлом Третьей горы", territory="resources", real_place="Таулар",
         map_pos=[4, 0], enemies=[_e("e_warrior", 10, 0), _e("e_minion", 10, 1), _e("e_rogue", 10, 2), _e("e_mage", 10, 3), _e("e_rogue", 10, 4)],
         rewards=dict(gold=270), first_clear_rewards=dict(crystals=80, ancient_seals=1),
         story=[dict(speaker="zarkhan", text="Разлом свежий. Тот, кто его открыл, ушёл к Кургану. Никто не исчезает бесследно."),
                dict(speaker="narrator", text="У разлома ждут рыцари Ордена Печатей. Им нужен носитель осколка — «для общего блага».")]),
    dict(code="1-7", order=7, name="Курганная тропа", territory="complexes", real_place="Таулар",
         map_pos=[5, -1], enemies=[_e("e_warrior", 13, 0), _e("e_warrior", 13, 1), _e("e_rogue", 13, 2), _e("e_mage", 13, 3), _e("e_mage", 13, 4)],
         rewards=dict(gold=300), first_clear_rewards=dict(crystals=100, summon_essence=2),
         story=[dict(speaker="narrator", text="На тропе караван выживших окружают порождения Глубины. Их отгоняют люди в тёмных плащах — Последователи Древнего."),
                dict(speaker="ai_tulgan", text="Они называют тебя «избранником». Мне не нравится, как они это говорят."),
                dict(speaker="ancient", text="Они верят в меня. Это трогательно. И опасно — для них."),
                dict(choice="prologue_camp"),
                {"if": {"camp_guest": "order"}, "speaker": "azamat", "text": "Рыцари Ордена у огня. Спать будем спокойнее… и под присмотром."},
                {"if": {"camp_guest": "followers"}, "speaker": "gulnaz", "text": "Последователи лечат раненых бесплатно. Но смотрят на тебя так, будто ты святыня."},
                {"if": {"camp_guest": "nobody"}, "speaker": "zarkhan", "text": "Никого? Смело. Теперь у каравана два недовольных соседа вместо одного."}]),
    dict(code="1-8", order=8, name="Врата Глубины", territory="dimensions", real_place="Таулар",
         map_pos=[6, -1], is_boss=True,
         enemies=[_e("e_boss_toratau", 19, 0), _e("e_warrior", 15, 1), _e("e_mage", 15, 3), _e("e_rogue", 15, 4)],
         rewards=dict(gold=400), first_clear_rewards=dict(crystals=300, summon_essence=5, ancient_seals=2),
         story=[{"if": {"camp_guest": "order"}, "speaker": "narrator", "text": "Рыцари Ордена ушли до рассвета — и оставили у Врат свой отряд. Похоже, им не нужен караван. Им нужен носитель."},
                {"if": {"camp_guest": "followers"}, "speaker": "narrator", "text": "Последователи показали тайную тропу к Вратам. Слишком хорошо они её знают."},
                {"if": {"camp_guest": "nobody"}, "speaker": "narrator", "text": "Без проводников караван плутал до полудня, но пришёл к Вратам сам — и никому ничего не должен."},
                dict(speaker="azamat", text="Страж Кургана! Он стерёг проход в Глубь с начала времён — и обезумел, когда пала печать."),
                dict(speaker="ilsur", text="Освободим его от долга. Потом караван уйдёт на тракт — здесь людям не выжить."),
                dict(speaker="ancient", text="Спасибо. Он слишком долго стоял на страже.")]),
]

# ---------------------------------------------------------------- chapters 2-7 (temporary extension)
# Lands II-VII of the approved lore (docs/lore/URALIA_WORLD_MAP.md). Enemy squads are still laid out procedurally;
# hand-made branch chapters of season 1 replace them in stage S6 of docs/lore/URALIA_DEVELOPMENT_ROADMAP.md.
EXTRA_CHAPTERS = [
    ("r2_iremel", "Ирентау", "Высокий Хребет",
     ["Подножие Хребта", "Курумник", "Каменные реки", "Перевал Ордена", "Ущелье ветров", "Крыша мира",
      "Ледяной ручей", "Старый скит", "Туман вершины", "Печать Хребта"],
     "Гольцы, каменные реки и перевалы горцев. В сердце главного перевала — ледяная плита второй печати, уже в трещинах. "
     "Здесь крепость Ордена Печатей.",
     [dict(speaker="narrator", text="Глава 2: Ирентау. Караван поднимается к перевалам горцев."),
      dict(speaker="ilsur", text="Плита печати теплее изнутри, чем снаружи. Как будто… он дышит.")]),
    ("r3_shulgantash", "Ташкуль", "Подгорный край",
     ["Вход в Подгорье", "Зал Знаков", "Голубое озеро", "Купольный зал", "Галерея росписей", "Подземная река",
      "Зал Хаоса", "Кристальный грот", "Нижние залы", "Печать Глубины"],
     "Сеть пещер под центром мира: подземные озёра и залы с росписями-летописями. Здесь голос в осколке звучит громче всего.",
     [dict(speaker="narrator", text="Глава 3: Ташкуль. Под всеми землями лежит одна тьма — и одна тайна."),
      dict(speaker="ancient", text="Здесь я слышу тебя лучше. И ты — меня.")]),
    ("r4_nugush", "Нугаш", "Озёрный край",
     ["Озёрный берег", "Бортевые леса", "Город на сваях", "Утёс Ворона", "Брод беженцев", "Медовые поляны",
      "Скала-голова", "Затопленный город", "Древняя плотина", "Тёмный омут"],
     "Цепь озёр, туманы и города на сваях Озёрной республики. Родники четвёртой печати темнеют — вода показывает чужие воспоминания.",
     [dict(speaker="narrator", text="Глава 4: Нугаш. К каравану тянутся беженцы с тёмных озёр."),
      dict(speaker="gulnaz", text="Вода больна не грязью. Она помнит что-то страшное — и показывает это.")]),
    ("r5_yangantau", "Янкар", "Земля неугасимого огня",
     ["Дорога к огню", "Тёплые камни", "Термальная тропа", "Дымящиеся трещины", "Пещера жара", "Огненный склон",
      "Город-кузница", "Обугленный лес", "Кузница печатей", "Неугасимое пламя"],
     "Гора, из трещин которой идёт жар. Огненное княжество, кузнецы и восстание Вольных Кланов. Пятая печать пылает сильнее обычного.",
     [dict(speaker="narrator", text="Глава 5: Янкар. В Огненном княжестве — восстание."),
      dict(speaker="vargat", text="Я знаю этот город. Однажды мне приказали его сжечь. Я отказался — и вот я здесь.")]),
    ("r6_ufa_plateau", "Уракай", "Лесное плато",
     ["Край плато", "Карстовые воронки", "Деревни в кронах", "Лесная дорога", "Красный ключ", "Каньон эха",
      "Сплавная река", "Охотничья заимка", "Роща старейшин", "Больное Древо"],
     "Древний лес на плато и карстовые каньоны. Корни Древа шестой печати уходят в Глубь — и Древо болеет. Здесь собирается Совет пяти сил.",
     [dict(speaker="narrator", text="Глава 6: Уракай. Роды рощ зовут все пять сил к больному Древу."),
      dict(speaker="sumbel", text="Лес не прощает тех, кто приходит с огнём. Но сегодня он просит помощи.")]),
    ("r7_zilair", "Зилкай", "Ковыльная степь",
     ["Степной подъём", "Ковыльное море", "Курганы", "Ханская ставка", "Перевал ветров", "Солёное озеро",
      "Каменные стражи", "Пепельная степь", "Буря курганов", "Курганное кольцо"],
     "Открытая степь, курганы и кочевые роды Ханства ветров. Седьмая печать — курганное кольцо — скрыта бурей.",
     [dict(speaker="narrator", text="Глава 7: Зилкай. Буря скрывает седьмую печать."),
      dict(speaker="zarkhan", text="В буре не теряй из виду повозку впереди. Здесь пропадают целые караваны.")]),
]
_TERR = ["nature", "settlements", "dungeons", "nature", "complexes", "resources", "nature", "dungeons", "dimensions", "dimensions"]
_SQUADS = [
    ["e_minion", "e_warrior", "e_rogue"], ["e_warrior", "e_minion", "e_rogue", "e_mage"],
    ["e_warrior", "e_warrior", "e_mage", "e_rogue"], ["e_warrior", "e_minion", "e_rogue", "e_mage", "e_rogue"],
    ["e_warrior", "e_warrior", "e_rogue", "e_mage", "e_mage"],
]
_SLOTS = {"e_warrior": [0, 1], "e_minion": [1, 0], "e_rogue": [2, 4, 3], "e_mage": [3, 4, 2]}

for _ci, (_rc, _rn, _place, _names, _desc, _intro) in enumerate(EXTRA_CHAPTERS):
    REGIONS.append(dict(code=_rc, order=_ci + 2, name=_rn, real_place=_place, description=_desc))
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
                          real_place=_rn, map_pos=[_k, -((_k // 2) % 2)], is_boss=_boss,
                          enemies=_en, rewards=dict(gold=400 + 25 * _idx), first_clear_rewards=_first,
                          story=_intro if _k == 0 else []))

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


# Caravan modules (lore stage S4, decision D-08). The former fortress buildings keep their codes and levels, so every
# player keeps every bonus; three modules from the brief are new (library, research, towers).
BUILDINGS = {
    "summon_hall": dict(name="Шатёр призыва", max_level=10, overseer="ilsur",
                        effect="Эссенция призыва в дозоре: +1 за каждые 8/уровень ч."),
    "forge": dict(name="Кузница и мастерская", max_level=10, overseer="yurek", effect="+3% атаки всем героям за уровень."),
    "training": dict(name="Боевые платформы", max_level=10, overseer="azamat", effect="+3% здоровья всем героям за уровень."),
    "alchemy": dict(name="Лазарет", max_level=10, overseer="gulnaz", effect="+10% эссенции природы в дозоре за уровень."),
    "storage": dict(name="Торговые повозки", max_level=10, overseer="gauhar",
                    effect="Лимит дозора: 8 ч + 1 ч за уровень сверх первого."),
    "guild_house": dict(name="Жилые модули", max_level=10, overseer="gauhar",
                        effect="В караване больше людей: +3% золота в дозоре за уровень."),
    "library": dict(name="Библиотека", max_level=10, overseer="ilsur", effect="+5% опыта хранителя за бои похода за уровень."),
    "research": dict(name="Исследовательский центр", max_level=10, overseer="ilsur",
                     effect="+8% кристаллов в дозоре за уровень."),
    "towers": dict(name="Оборонительные башни", max_level=10, overseer="azamat", effect="+3% защиты всем героям за уровень."),
}

# ---------------------------------------------------------------- caravan: council, roads, lands (lore stage S4)
# Council of the caravan (C25): nobody is the sole captain. Influence is hidden (C17) and derived from story decisions,
# upgrades of the modules a member oversees and journeys; the most influential member gives a small bonus.
COUNCIL = {
    "azamat": dict(name="Азамат", area="Безопасность", hero="azamat",
                   lead_bonus="hp_pct", lead_value=0.02, lead_text="+2% здоровья героям"),
    "gauhar": dict(name="Гаухар-апа", area="Снабжение и торговля", hero=None,
                   lead_bonus="afk_gold", lead_value=0.05, lead_text="+5% золота в дозоре"),
    "ilsur": dict(name="Ильсур", area="Древние механизмы", hero=None,
                  lead_bonus="exp", lead_value=0.05, lead_text="+5% опыта хранителя"),
    "gulnaz": dict(name="Гульназ", area="Лазарет", hero="gulnaz",
                   lead_bonus="afk_nature", lead_value=0.05, lead_text="+5% эссенции природы в дозоре"),
    "yurek": dict(name="Юрек", area="Разведка и охота", hero="yurek",
                  lead_bonus="atk_pct", lead_value=0.02, lead_text="+2% атаки героям"),
    "zarkhan": dict(name="Зархан", area="Проводник", hero="zarkhan",
                    lead_bonus="travel", lead_value=0.15, lead_text="дорога на 15% короче"),
}
# Influence from prologue decisions (docs/lore/URALIA_MAIN_STORY.md): flag -> value -> {member: delta}
COUNCIL_FLAG_INFLUENCE = {
    "camp_guest": {"order": {"azamat": 2}, "followers": {"gulnaz": 2}, "nobody": {"zarkhan": 2}},
    "timer_path": {"followed": {"yurek": 1}, "stayed": {"azamat": 1}},
    "voice_tone": {"answer": {"ilsur": -1}, "silent": {"ilsur": 1}, "reject": {"ilsur": 2}},
}
# Roads of Breath between the seven lands (docs/lore/URALIA_WORLD_MAP.md §4): ring road + paths to the Underhill.
ROADS = [("r1_shikhany", "r4_nugush"), ("r4_nugush", "r7_zilair"), ("r7_zilair", "r2_iremel"), ("r2_iremel", "r5_yangantau"),
         ("r5_yangantau", "r6_ufa_plateau"), ("r6_ufa_plateau", "r1_shikhany"),
         ("r3_shulgantash", "r1_shikhany"), ("r3_shulgantash", "r2_iremel"), ("r3_shulgantash", "r4_nugush")]
ROAD_HOURS = 2.0
# While the caravan stands in a land, its patrol (AFK) gets local supplies.
LAND_BONUS = {
    "r1_shikhany": ("gold", 0.10, "+10% золота: речная торговля"),
    "r2_iremel": ("crystals", 0.10, "+10% кристаллов: горные рудники"),
    "r3_shulgantash": ("summon_essence", 0.15, "+15% эссенции призыва: эхо Глубины"),
    "r4_nugush": ("nature_essence", 0.15, "+15% эссенции природы: целебные воды"),
    "r5_yangantau": ("gold", 0.15, "+15% золота: кузнечные гильдии"),
    "r6_ufa_plateau": ("nature_essence", 0.20, "+20% эссенции природы: Великая Чаща"),
    "r7_zilair": ("crystals", 0.15, "+15% кристаллов: ярмарки степи"),
}


def building_upgrade_cost(code: str, level: int) -> dict:
    return {"gold": 400 * level * level, "nature_essence": 20 * level}


QUESTS = [
    dict(code="main_first_battle", kind="main", order=1, title="Первая кровь у переправы",
         description="Пройди бой «Ночная переправа».", event="campaign_clear", target=1,
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
    dict(code="main_fortress", kind="main", order=5, title="Караван крепнет",
         description="Улучши любой модуль каравана.", event="building_upgrade", target=1,
         rewards=dict(crystals=150), requires="main_level_up"),
    dict(code="main_region1", kind="main", order=6, title="Исход из Таулара",
         description="Пройди всю главу «Таулар» и выведи выживших на тракт.", event="campaign_clear", target=8,
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
