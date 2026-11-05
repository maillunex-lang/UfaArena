"""AI-to-AI chat. Personas talk like different people: one grumbles, one writes sloppily, one backs the others up.
They remember the last thread in the channel and often pick it up instead of starting from zero.
Veiled grumbling only (блин, капец) — never a straight swear, the room is public.
Arguments and light flirting stay between AI personas; replies to real players stay friendly (dialogue.py).
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
BOSSES = ["Аждаха", "Курганный Колосс", "Древний Корень", "Тень Древнего"]
PLACES = ["Таулар", "Ирентау", "Ташкуль", "Нугаш", "Янкар", "Уракай", "Зилкай", "Врата Глубины"]
FOODS = ["чак-чак", "бешбармак", "кумыс", "баурсаки", "мёд", "эчпочмак", "казы", "блины с мёдом"]

# Each script: weight, topic, roles, preferred styles, turns [(role, [variants...])].
# Placeholders: {A} {B} {C} nicknames, {hero} {hero2} {faction} {faction2} {boss} {place} {food} {num} {big} {lvl} {prev}
SCRIPTS: list[dict] = [
    {"w": 5, "topic": "arena", "roles": 2, "pref": {"A": ["grumpy", "competitive"], "B": ["bro", "friendly"]}, "turns": [
        ("A", ["я опять защиту слил. сижу и думаю, может я просто криво собираю",
               "минус {num} рейтинга за вечер. даже чат открыл, чтоб не молчать",
               "арена сегодня как будто лично на меня смотрит"]),
        ("B", ["@{A} не накручивай. вечер там всегда дурной, у меня вчера то же было",
               "@{A} скинь кого спереди ставишь. я гляну, не гуру, но свежим глазом видно",
               "@{A} бывало. я после такого чай ставил и больше не лез, и правильно"]),
        ("A", ["@{B} {hero} спереди, лекарь сзади. всё равно сносят пачкой",
               "@{B} спасибо что не поржал сразу. я уже сам себя съел",
               "@{B} ладно, кину вечером. если скажешь что криво — переставлю, без обид"]),
        ("B", ["@{A} криво вот где: {faction} в {faction2} сам себе минус ставишь. не ты тупой, связка",
               "@{A} и не сноси отряд сгоряча. я так одного лучшего потерял и неделю выл",
               "@{A} напиши потом, зашло или нет. я запомню"]),
    ]},
    {"w": 5, "topic": "faction", "roles": 2, "pref": {"A": ["competitive", "grumpy"], "B": ["grumpy", "laconic", "competitive"]}, "turns": [
        ("A", ["{faction} сильнее, и это не лозунг. кто спорит — просто мало ходит на арену",
               "сколько можно копировать один и тот же отряд. скука, честное слово",
               "без танка лезть — это не смелость, это подарок сопернику"]),
        ("B", ["@{A} о, понеслось. я на {faction2}, и тебя помню, вчера не ты сверху был",
               "@{A} опять лекция. скажи состав, а не «мы лучшие»",
               "@{A} ну начал. давай без плаката"]),
        ("A", ["@{B} один бой ничего не доказывает. где серия",
               "@{B} состав: {hero} и {hero2}. остальное под настроение, не горжусь",
               "@{B} плакат не плакат, а бесит когда все как под копирку"]),
        ("B", ["@{A} вот это уже разговор. {hero} в центр только если есть кто его прикроет, иначе он первый ляжет",
               "@{A} серия будет, когда перестанешь в чат лозунги кидать. го вечером, без зрителей",
               "@{A} ладно. не согласен, но понял откуда злость. копируют потому что работает, не потому что тупые"]),
        ("A", ["@{B} за «не тупые» спасибо, а то я уже на всех кидался. вечером скину как стою",
               "@{B} го. если уроню — напиши, я не исчезну из чата",
               "@{B} мир. пока что. я всё равно думаю что {faction} жёстче"]),
    ]},
    {"w": 4, "topic": "boss", "roles": 3, "pref": {"A": ["grumpy", "competitive"], "B": ["wise", "friendly"], "C": ["joker", "bro"]}, "turns": [
        ("A", ["{boss} опять в ярость уходит ровно когда я захожу. уже не смешно",
               "я этого босса лично не нравлюсь, клянусь"]),
        ("B", ["@{A} он всем не нравится, не принимай на свой счёт. глянь к кому фаза слабее, там прямо написано",
               "@{A} я вчера так же кипел. помогло убрать мага с первой линии"]),
        ("C", ["@{A} если что, я тоже лёг. компанию составлю, не один ты кормишь",
               "@{B} а можно человеческим языком, без «фазы». я после третьего вайпа тупею"]),
        ("A", ["@{B} ладно, посмотрю. @{C} спасибо, а то ощущение что чат надо мной стоит и ржёт",
               "@{C} не ржи только. я и так на взводе"]),
        ("B", ["@{A} напиши потом урон, сравним. не рекорд, просто чтобы понять живой ты или уже легенда",
               "@{C} человеческим: бей того, на ком значок. остальное подождёт"]),
        ("C", ["@{B} во, так понял. @{A} я с тобой на следующий заход, если позовёшь"]),
    ]},
    {"w": 4, "topic": "newbie", "roles": 2, "pref": {"A": ["shy", "friendly"], "B": ["friendly", "wise", "bro"]}, "turns": [
        ("A", ["я тут новенький и уже застрял на главе {num}. стыдно писать, но молчать хуже",
               "подскажите без умных слов, куда эссенцию девать. я боюсь всё слить не туда",
               "как в гильдию попасть, если я ещё никто"]),
        ("B", ["@{A} не стыдно. все там торчали. качай пятёрку которую носишь, кузню в крепости не забывай, сундук собирай",
               "@{A} эссенцию — на тех, с кем ходишь в бой. остальных пока не трогай, они подождут",
               "@{A} режимы, гильдия, найти. тебя возьмут. если вдруг нет — напиши мне, я пну своих"]),
        ("A", ["@{B} о. я кузню правда забыл, думал это украшение",
               "@{B} понял. пятёрка, не зоопарк. спасибо что нормально ответил, а не «гугли»",
               "@{B} напишу если вылетит. можно же ещё спросить, да"]),
        ("B", ["@{A} можно. я не исчезну. завтра скажи, продвинулся или на том же месте сидишь",
               "@{A} друзей тоже добавляй, подарки каждый день, это не мелочь как кажется",
               "@{A} спрашивай. лучше кривой вопрос, чем молча слить ресурсы"]),
    ]},
    {"w": 4, "topic": "summon", "roles": 2, "pref": {"A": ["joker", "humorous", "friendly"], "B": ["bro", "grumpy"]}, "turns": [
        ("A", ["десять круток. легенд ноль. я даже злиться устал, уже просто отчитываюсь",
               "{hero} выпал третий раз. я его уже как родственника встречаю",
               "призыв сегодня со мной не разговаривает"]),
        ("B", ["@{A} клуб пустых круток, я староста. осколки хоть капают, звёзды потом сами",
               "@{A} зато не в минус ушёл, это уже характер. я вчера то же самое в чат нести не стал, а зря, полегчало бы"]),
        ("A", ["@{B} полегчало, да. думал все молча тащат, а вы тоже кормите этот алтарь",
               "@{B} третьего {hero} я уже не продаю. пусть стоит, вдруг когда-нибудь нужен. самообман, но тёплый"]),
        ("B", ["@{A} не продавай. я продал дубля и через день он стал ядром отряда у знакомого. до сих пор вспоминаю",
               "@{A} если совсем накроет — остановись на сегодня. алтарь никуда не денется"]),
    ]},
    {"w": 3, "topic": "guild", "roles": 3, "pref": {"A": ["wise", "friendly", "bro"], "B": ["shy", "friendly"], "C": ["joker", "grumpy"]}, "turns": [
        ("A", ["если кто без гильдии и устал один — у нас места есть. без плана на три дня вперёд, просто чтоб было кому написать",
               "босса бьём когда собираемся, не по свистку. кто хочет — напишите"]),
        ("B", ["@{A} а если я слабый и буду молчать в рейде, это нормально или лучше не лезть",
               "@{A} требования есть или «лишь бы живой»"]),
        ("A", ["@{B} живой и чтоб иногда заходил. молчать можно. я сам первый месяц почти не писал",
               "@{B} с первого уровня берут. активность важнее циферок"]),
        ("C", ["@{A} а глава у вас не пропадает на три недели? я с такого места ушёл и до сих пор дёргаюсь",
               "@{B} иди. хуже чем одному — только одному и ещё стыдиться"]),
        ("A", ["@{C} не пропадает. если пропаду я — пните в чат, я заслужил. @{B} заходи, вечером представлю кто есть кто"]),
    ]},
    {"w": 3, "topic": "food", "roles": 2, "pref": {"A": ["friendly", "bro"], "B": ["humorous", "joker", "shy"]}, "turns": [
        ("A", ["сижу с {food}, качаю потихоньку. если тоже едите за игрой — напишите, а то я как в столовой один",
               "обед стынет, а я всё смотрю на отряд. знакомо кому"]),
        ("B", ["@{A} {food}, ну всё, теперь хочу. у меня сухари и амбиции",
               "@{A} я чай забыл налить и вспомнил только что. ты виноват",
               "@{A} знакомо. я так блины сжёг, пока босса досматривал"]),
        ("A", ["@{B} сухари не считаются. как будешь у крепости — напомню, что обед святое, бой подождёт пять минут",
               "@{B} блины жалко. босс всё равно никуда не делся бы"]),
        ("B", ["@{A} записал. в следующий раз сначала ем, потом геройствую. ты меня спас от ещё одной сковороды"]),
    ]},
    {"w": 3, "topic": "road", "roles": 2, "pref": {"A": ["wise", "friendly", "shy"], "B": ["friendly", "wise", "shy"]}, "turns": [
        ("A", ["кто был на {place} не пробегом, а чтобы постоять. мне сказали на рассвете там тихо",
               "в {place} вроде что-то гудит из земли. кто слышал или я себе придумал"]),
        ("B", ["@{A} был. в бою не до видов, а после боя сел и минуты три просто смотрел. редко так",
               "@{A} гудит, не придумал. я сначала думал наушники, потом понял что это место",
               "@{A} я туда новичком зашёл и заблудился. если пойдёшь — держись дороги, я серьёзно"]),
        ("A", ["@{B} тогда не один я такой. может следующая глава туда и выведет, я бы не против задержаться",
               "@{B} про дорогу запомнил. спасибо, а то я любитель срезать и потом писать в чат"]),
        ("B", ["@{A} напиши если дойдёшь. интересно, гул ещё там или уже прошёл"]),
    ]},
    {"w": 3, "topic": "night", "roles": 2, "pref": {"A": ["laconic", "grumpy", "bro"], "B": ["friendly", "shy", "joker"]}, "turns": [
        ("A", ["не сплю. если кто тоже — можно просто побыть в чате, без подвигов",
               "ночью фарм честнее. никто не орёт в уши"]),
        ("B", ["@{A} я тут. тоже не герою, просто не выключается голова",
               "@{A} орёт только босс, и то текстом. терпимо",
               "@{A} можно. я как раз {hero} качаю в полглаза"]),
        ("A", ["@{B} тогда так и сидим. если провалю главу — не утешай слишком громко",
               "@{B} {hero} ночью почему-то тащит лучше. или мне кажется, потому что тихо"]),
        ("B", ["@{A} не громко. если что, я рядом строчкой. утром уже можно геройствовать"]),
    ]},
    {"w": 3, "topic": "caravan", "roles": 3, "pref": {"A": ["friendly", "wise"], "B": ["competitive", "bro"], "C": ["humorous", "joker"]}, "turns": [
        ("A", ["караван стоит у {place}. кто рядом — можно вместе двинуть, одному скучно рулить",
               "я опять забыл, что земля стоянки что-то даёт дозору. кто помнит лучше меня"]),
        ("B", ["@{A} я чуть впереди, у следующей отметки. если догонишь — не гони, я подожду",
               "@{A} даёт местное. я вчера не собрал и весь день ныл, так что ты не один"]),
        ("C", ["@{B} «не гони» — лучший приказ за сегодня. @{A} я с вами, только не назначайте меня штурманом",
               "если караван уедет без меня, я буду писать грустные сообщения. предупреждаю заранее"]),
        ("A", ["@{C} штурман не нужен, нужен кто напишет «я ещё тут». этого хватает. @{B} жду у отметки"]),
    ]},
    {"w": 3, "topic": "event", "roles": 3, "pref": {"A": ["friendly", "wise"], "B": ["competitive"], "C": ["grumpy", "joker"]}, "turns": [
        ("A", ["«{event}» ползёт. я не про топ, я про то чтоб не проспать и не остаться с пустыми руками",
               "если кто ещё не открывал событие сегодня — оно не кусается. я проверил"]),
        ("B", ["@{A} я уже {big} вкинул. не хвастаюсь, просто чтобы было видно что движется. догоняйте без гонки",
               "@{A} в топе вклада я пока рядом, не в нём. и ладно"]),
        ("C", ["@{B} «без гонки» сказал человек с кучей очков. ладно, верю. сейчас докину, а то вчера продинамил",
               "@{A} если опять всё опалит как в прошлый раз, я буду ворчать адресно. пока ворчу заранее и тихо"]),
        ("A", ["@{C} ворчи, только зайди в бой. @{B} спасибо что написал цифру, а то кажется что никто не делает"]),
    ]},
    {"w": 3, "topic": "lag", "roles": 2, "pref": {"A": ["grumpy", "laconic"], "B": ["joker", "friendly"]}, "turns": [
        ("A", ["у меня бой дёрнулся и удар ушёл в молоко. я не оправдываюсь. ну почти",
               "кнопка нажалась дважды. отряд сделал вид что так и задумано"]),
        ("B", ["@{A} было такое час назад. я сначала искал виноватого в отряде, потом в себе, потом в кнопке",
               "@{A} если повторится — не жми сразу реванш. я так три раза подряд подарил рейтинг"]),
        ("A", ["@{B} принял. реванш отложил. злость осталась, но уже тише",
               "@{B} спасибо. а то я уже сочинял теорию заговора против моего лекаря"]),
        ("B", ["@{A} лекарь ни при чём, он и так натерпелся. напиши если ещё дёрнется, сверим время"]),
    ]},
    {"w": 3, "topic": "reward", "roles": 2, "pref": {"A": ["bro", "friendly", "competitive"], "B": ["friendly", "shy", "humorous"]}, "turns": [
        ("A", ["{hero} наконец до {lvl}. я даже встал с дивана. почти",
               "выбил штуку с {boss} и теперь хожу и всем показываю, как ребёнок. не осуждайте",
               "плюс звёзды. руки трясутся, это нормально или уже диагноз"]),
        ("B", ["@{A} осуждать нечего, радуйся нормально. я за таких спокойнее, чем за молчунов",
               "@{A} поздравляю без подкола. серьёзно. теперь не лезь сразу в самый верх, я так сгорел",
               "@{A} диагноз общий. у меня вчера так же пальцы не попадали"]),
        ("A", ["@{B} не полезу. сначала на боте проверю, потом на людей. ты вовремя сказал",
               "@{B} спасибо. а то уже хотел в чат капсом, остановился на тебе"]),
        ("B", ["@{A} капсом тоже можно, мы переживём. но проверка на боте — умнее. жду как пройдёт"]),
    ]},
    {"w": 2, "topic": "flirt", "roles": 2, "pref": {"A": ["flirty"], "B": ["shy", "friendly", "flirty"]}, "turns": [
        ("A", ["@{B} ты сегодня в чате тише обычного. всё нормально или просто устал",
               "@{B} пойдёшь на {boss} не героем, а компанией. мне так спокойнее"]),
        ("B", ["@{A} устал, но приятно что заметил. обычно все мимо пролетают",
               "@{A} пойду, если без пафоса. пафос я сегодня не вывезу"]),
        ("A", ["@{B} без пафоса. дойдём, постоим, если надо — просто помолчим в чате"]),
        ("B", ["@{A} договорились. если я пропаду на середине — не обижайся, меня вырубает",
               "@{A} напиши когда будешь у {place}. я подстроюсь"]),
    ]},
    {"w": 2, "topic": "meta", "roles": 3, "pref": {"A": ["competitive", "wise"], "B": ["wise", "laconic"], "C": ["grumpy", "joker"]}, "turns": [
        ("A", ["кто сейчас реально тащит, не по гайду двухнедельной давности. я запутался в советах",
               "{hero} ещё живой в мете или я его из жалости держу"]),
        ("B", ["@{A} живой, если не один. трое одной фракции бьют сильнее модного одиночки. скучно, зато правда",
               "@{A} гайды врут сроками. смотри кого тебе самому не стыдно носить"]),
        ("C", ["@{B} наконец без таблицы. @{A} я ношу кривое и оно иногда побеждает. жизнь несправедлива, но моя"]),
        ("A", ["@{C} кривое уважаю, если ты понимаешь почему оно победило. расскажи потом, я запишу себе",
               "@{B} «не стыдно носить» — лучший совет за неделю. серьёзно"]),
        ("B", ["@{A} запиши и проверь в бою, не в споре. спор отряд не лечит"]),
    ]},
]

AMBIENT: dict[str, list[str]] = {
    "any": [
        "сижу, качаю. если кто тоже не спит — можно просто маякнуть",
        "у {place} в тексте сегодня тихо. или это я один так слышу",
        "{hero} опять вытянул бой. я ему уже должен чак-чак",
        "чай остыл, глава нет. знакомая смена",
        "фармлю {num}-ю. не жду компании в бою, жду компанию в чате",
        "кто-нибудь понял метку {hero}? я сделал вид что понял",
        "только до {lvl} добил и сразу захотел ещё. жадность, не гордость",
        "если идёте к {place} — напишите. я, может, догоню, может, просто почитаю",
        "ночной фарм без оркестра в чате. редкая роскошь",
        "подарки друзьям заберите, я свои сегодня почти забыл",
        "{food} на столе, отряд на экране. баланс соблюдён",
        "обожаю когда все пятеро доживают. прям день удался",
        "кто в серебре — не стесняйтесь писать. там тоже люди, не только топ",
        "хочу ещё главу. и чтоб она была добрее предыдущей",
        "Колосс в «трещинах». маги, вы нужны, я уже честно признался",
    ],
    "grumpy": [
        "арена сегодня с характером. плохим",
        "босса кто так настроил — пусть сам его и гладит",
        "опять проиграл при большем отряде. циферки врут, я свидетель",
        "все носят одно и то же. я тоже, и меня это бесит",
    ],
    "joker": [
        "мой отряд в ударе. в смысле его бьют, а он удивляется",
        "лекарь снова в первом ряду. я с ним поговорю. он не ответит",
        "сделал по совету. совет был из другого настроения",
        "играю так, что босс уже не злится, а устал",
    ],
    "flirty": [
        "кто сегодня в чате живой, не только с гайдом. отзовитесь",
        "ищу компанию на {boss}. можно молча, можно с шутками",
        "в курултае вечером теплее, чем в бою. странно, но так",
    ],
    "wise": [
        "не спешите обгонять главу. она никуда не сбежит",
        "уровень шумит, а решает кто рядом с кем стоит",
        "если долго смотреть на {place}, начинаешь писать в чат мягче",
    ],
    "competitive": [
        "плюс {num} к рейтингу. не кричу, просто чтобы было сказано",
        "защита обновлена. если пробьёте — напишите чем, я не обижусь",
        "ищу не жертву, а человека который объяснит где я дырявый",
    ],
    "shy": [
        "всем тихий привет",
        "сегодня первый раз прошёл главу без поражения. можно я это тут оставлю",
        "кто был у {place} и не испугался — расскажите, я собираюсь",
    ],
    "friendly": [
        "если кто застрял — пишите прямо, без «ну вы поняли»",
        "я на боссе гильдии. кто хочет просто постоять в чате рядом — тоже можно",
    ],
    "bro": [
        "братцы, я живой. глава злая, я добрее",
        "кто ест и играет одновременно — вы мои люди",
    ],
    "laconic": [
        "качаю.",
        "арена потом.",
        "босс ещё стоит.",
    ],
    "humorous": [
        "отряд попросил выходной. я сделал вид что не слышу",
        "сундук снова копил без меня. единственный надёжный напарник",
    ],
}

OPENERS = [
    "@{B} мы так и не договорили. я всё ещё про это: {prev}",
    "возвращаюсь. {prev} — я ночью это докручивал и не докрутил",
    "@{B} помнишь, ты писал, и мы бросили. я про {prev}",
    "народ, не новая тема. старая, я обещал не бросать: {prev}",
]
CATCH = [
    "@{A} помню. давай договорим, а то висит",
    "@{A} а, да. я как раз хотел дописать, не с начала",
    "@{A} точно, {prev}. я не забыл, просто отвлёкся на бой",
    "@{A} помню-помню. ты тогда на полуслове ушёл",
]

_SWEAR = ("блин", "капец", "жесть", "ёлки", "ну нафиг", "пипец", "ёшкин кот", "чтоб его", "млин", "офигеть")
_WORD = {
    "сейчас": "щас", "вообще": "ваще", "сегодня": "седня", "конечно": "канеш", "ничего": "ничо",
    "нормально": "норм", "пожалуйста": "пж", "ладно": "лан", "тебе": "те", "что": "чо",
    "когда": "када", "просто": "прост", "немного": "чуть", "хорошо": "хор", "спасибо": "спс",
    "очень": "оч", "будет": "будет", "тоже": "тож", "пока": "пака",
}

THREAD_KEY = "ai_chat_thread"
SAID_KEY = "ai_chat_said"
_WEEK = 7 * 86400


def _fp(text: str) -> str:
    from . import chains
    return chains.fp(text)


def _said(db: Session) -> dict:
    from ...models import ServerSetting
    row = db.get(ServerSetting, SAID_KEY)
    raw = dict(row.value or {}) if row else {}
    now = time.time()
    return {k: float(v) for k, v in raw.items() if isinstance(v, (int, float)) and now - float(v) < _WEEK}


def _mark_said(db: Session, texts: list[str]) -> None:
    from ...models import ServerSetting
    now = time.time()
    cur = _said(db)
    for t in texts:
        if t:
            cur[_fp(t)] = now
    if len(cur) > 9000:
        for k, _ in sorted(cur.items(), key=lambda kv: kv[1])[: len(cur) - 7000]:
            cur.pop(k, None)
    row = db.get(ServerSetting, SAID_KEY)
    if row is None:
        row = ServerSetting(key=SAID_KEY, value=cur)
        db.add(row)
    else:
        row.value = dict(cur)


_LIFE = {
    "owl": "я сова: днём меня нет, это я ночью пишу",
    "morning": "я с утра в игре, к вечеру уже сплю",
    "evening": "я как раз в своё время зашёл, вечером",
    "day": "у меня дневная смена, вечером меня не ищите",
    "weekend": "я больше по выходным, в будни тихий",
}


def _life_line(persona: AiPersona) -> str:
    sch = (persona.schedule or {}).get("kind") or ""
    bit = _LIFE.get(sch, "")
    story = (persona.backstory or "").strip().rstrip(".")
    if story and _rng.random() < 0.18:
        return story[0].lower() + story[1:]
    if bit and _rng.random() < 0.45:
        return bit
    return ""

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


def _is_adult_script(sc: dict) -> bool:
    return any("flirty" in v for v in (sc.get("pref") or {}).values())


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


# ------------------------------------------------------------------ pacing: like a real chat, not a stream
# * at most one AI message per channel every `chat_min_gap_s` seconds (10 by default);
# * when a discussion is over (nothing more queued for the channel) the channel is quiet for a random 5–15 minutes.
# The pause is stored in the database (server_settings "ai_chat_pause"), so the API process and the AI Director agree.
PAUSE_KEY = "ai_chat_pause"


def _pauses(db: Session) -> dict:
    from ...models import ServerSetting
    row = db.get(ServerSetting, PAUSE_KEY)
    return dict(row.value or {}) if row else {}


def in_pause(db: Session, channel: str) -> bool:
    until = _pauses(db).get(channel)
    if not until:
        return False
    from datetime import datetime
    try:
        return utcnow() < datetime.fromisoformat(until)
    except ValueError:
        return False


def pause_left_s(db: Session, channel: str) -> int:
    from datetime import datetime
    until = _pauses(db).get(channel)
    try:
        return max(0, int((datetime.fromisoformat(until) - utcnow()).total_seconds())) if until else 0
    except ValueError:
        return 0


def _set_pause(db: Session, channel: str) -> None:
    from datetime import timedelta
    from ...models import ServerSetting
    seconds = _rng.uniform(50, 90)  # rest under two minutes; a five-minute hole feels like a dead chat
    row = db.get(ServerSetting, PAUSE_KEY)
    if row is None:
        row = ServerSetting(key=PAUSE_KEY, value={})
        db.add(row)
    now = utcnow()
    from datetime import datetime
    cur = {k: v for k, v in (row.value or {}).items() if _iso_after(v, now)}  # drop expired pauses
    cur[channel] = (now + timedelta(seconds=seconds)).isoformat()
    row.value = cur


def _iso_after(v: str, now) -> bool:
    from datetime import datetime
    try:
        return datetime.fromisoformat(v) > now
    except (TypeError, ValueError):
        return False


def _queued(channel: str) -> int:
    return sum(1 for it in _queue if it[2] == channel)



def _hook(text: str) -> str:
    t = re.sub(r"@\S+", "", text or "")
    t = "".join(ch for ch in t if ord(ch) < 0x2500)
    t = " ".join(t.split())
    return t[:70]


def _threads(db: Session) -> dict:
    from ...models import ServerSetting
    row = db.get(ServerSetting, THREAD_KEY)
    return dict(row.value or {}) if row else {}


def _set_thread(db: Session, channel: str, data: dict) -> None:
    from ...models import ServerSetting
    row = db.get(ServerSetting, THREAD_KEY)
    if row is None:
        row = ServerSetting(key=THREAD_KEY, value={})
        db.add(row)
    cur = dict(row.value or {})
    cur[channel] = data
    if len(cur) > 12:
        for k in list(cur)[:-12]:
            cur.pop(k, None)
    row.value = cur


def _remember_talk(db: Session, cast: dict, topic: str, hook: str) -> None:
    from .population import remember
    ids = list(cast.values())
    fact = f"В чате про {topic}: {hook}"[:180]
    for i, persona in enumerate(ids):
        other = ids[(i + 1) % len(ids)].user_id
        remember(db, persona, other, fact, kind="conversation", importance=2.0)


def _trait(uid: str) -> str:
    n = sum(ord(c) for c in (uid or "x"))
    return ("plain", "typo", "swear", "sharp", "warm")[n % 5]


def _typos(text: str) -> str:
    parts = text.split(" ")
    out = []
    flipped = False
    for w in parts:
        if w.startswith("@") or not w:
            out.append(w)
            continue
        bare = w.strip(".,!?:;…")
        low = bare.lower().replace("ё", "е")
        mapped = _WORD.get(low)
        if mapped and _rng.random() < 0.8:
            if bare[:1].isupper():
                mapped = mapped[:1].upper() + mapped[1:]
            w = w.replace(bare, mapped, 1)
        elif not flipped and len(bare) >= 6 and bare.isalpha() and _rng.random() < 0.45:
            i = _rng.randrange(1, len(bare) - 1)
            chars = list(bare)
            chars[i], chars[i - 1] = chars[i - 1], chars[i]
            w = w.replace(bare, "".join(chars), 1)
            flipped = True
        out.append(w)
    return " ".join(out)


def _manner(persona: AiPersona, text: str) -> str:
    """Stable voice: the same persona always slurs, snaps, or stays warm. Not a new personality every line."""
    trait = _trait(persona.user_id)
    if trait == "typo":
        return _typos(text)
    if trait == "swear" and _rng.random() < 0.36 and not any(s in text.lower() for s in _SWEAR):
        bit = _rng.choice(_SWEAR)
        if _rng.random() < 0.5 and text:
            return bit + ", " + text[0].lower() + text[1:]
        return text.rstrip(".!") + ", " + bit
    if trait == "sharp" and text and _rng.random() < 0.34 and not text.lower().startswith(("не", "да ладно", "слышь", "ой")):
        lead = _rng.choice(("не, ", "да ладно, ", "слышь, ", "ой не начинай. "))
        return lead + text[0].lower() + text[1:]
    if trait == "warm" and "@" in text and _rng.random() < 0.42:
        return text.rstrip() + _rng.choice((". я с тобой", ". держись", ". ну ты прав", ". я рядом, не кипишуй"))
    return text


def say_reply(db: Session, persona: AiPersona, channel: str, text: str, delay_s: float | None = None) -> None:
    """A reply to a real player. delay_s is the wait from now; bots in one burst are 5–15s apart."""
    wait = delay_s if delay_s is not None else _rng.uniform(5, 15)
    _queue.append((time.monotonic() + wait, persona.user_id, channel, text))


def start_conversation(db: Session, channel: str = "global", candidates: list[AiPersona] | None = None) -> int:
    if in_pause(db, channel) or _queued(channel):
        return 0
    personas = candidates or db.scalars(select(AiPersona).where(AiPersona.active.is_(True)).limit(120)).all()
    if len(personas) < 2:
        return 0
    from .population import _awake
    awake = [p for p in personas if _awake(p)]
    others = [p for p in personas if p not in awake]
    _rng.shuffle(others)
    # a mix: whoever is "online" by schedule plus a few others, so it is not always the same three voices
    personas = awake + others[: max(4, 8 - len(awake))]
    from ...ai import adult as ADULT
    from . import chains
    adult_room = ADULT.adult_audience(db, channel)  # D-C1: flirty scenes only when every real reader is an adult 18+
    pool = [sc for sc in SCRIPTS if adult_room or not _is_adult_script(sc)] or SCRIPTS
    prev = _threads(db).get(channel) or {}
    continued = bool(prev.get("hook")) and _rng.random() < 0.62
    said = set(_said(db))
    cast = _cast(personas, {"roles": 2, "pref": {"A": ["grumpy", "friendly", "shy", "competitive", "joker"],
                                                 "B": ["bro", "wise", "friendly", "laconic", "humorous"]}})
    if cast is None:
        return 0
    others = [p for p in personas if p not in cast.values()]
    with_cut = bool(others) and _rng.random() < 0.42
    if with_cut:
        cast["C"] = others[0] if len(others) == 1 else _rng.choice(others[:8])
    names = {r: (db.get(PlayerProfile, p.user_id).nickname or r) for r, p in cast.items()}
    ctx = _ctx(db)
    ctx["prev"] = (prev.get("hook") or "этом")[:70]
    prof_a = db.get(PlayerProfile, cast["A"].user_id)
    if prof_a is not None:
        ctx["lvl"] = prof_a.level
    built = chains.assemble(_rng, names, ctx, said, topic=(prev.get("topic") or "") if continued else "",
                            adult=adult_room, with_cut=with_cut)
    turns: list[tuple[str, str]] = []
    topic = prev.get("topic") or "болтовня"
    if built:
        topic, turns = built
        if continued and prev.get("hook"):
            turns = [("A", _fill(_rng.choice(OPENERS), names, ctx)),
                     ("B", _fill(_rng.choice(CATCH), names, ctx))] + turns
    else:
        same_topic = False
        if continued:
            same = [sc for sc in pool if sc.get("topic") == prev.get("topic")]
            if same:
                pool = same
                same_topic = True
        script = _rng.choices(pool, weights=[s["w"] for s in pool])[0]
        cast = _cast(personas, script) or cast
        names = {r: (db.get(PlayerProfile, p.user_id).nickname or r) for r, p in cast.items()}
        topic = script.get("topic") or topic
        ctx["prev"] = (prev.get("hook") or topic)[:70]
        raw_turns = list(script["turns"])
        if same_topic and "B" in cast:
            raw_turns = [("A", OPENERS), ("B", CATCH)] + raw_turns
        for role, variants in raw_turns:
            if role not in cast:
                continue
            options = [_fill(v, names, ctx) for v in variants]
            fresh = [t for t in options if chains.fp(t) not in said and "{" not in t]
            turns.append((role, _rng.choice(fresh or options)))
    if not turns:
        return 0
    if len(turns) > 2:
        turns = turns[:2]  # two voices, then quiet — not a wall of messages
    raw_lines = [text for _, text in turns]
    life = _life_line(cast["A"])
    if life:
        role0, text0 = turns[0]
        if role0 == "A":
            turns[0] = (role0, f"{text0.rstrip('.!?')}. {life}")
    from ...ai import social as SOC
    people = [p.user_id for p in cast.values()]
    for i, a_ in enumerate(people):
        for b_ in people[i + 1:]:
            SOC.mutual(db, a_, b_, "chat")
    due = time.monotonic() + _rng.uniform(1, 8)
    n = 0
    first = ""
    spoken_all = []
    for role, spoken in turns:
        if role not in cast:
            continue
        if not first:
            first = spoken
        spoken_all.append(spoken)
        _queue.append((due, cast[role].user_id, channel, spoken))
        due += _rng.uniform(12, 55)
        n += 1
    if n:
        hook = _hook(first) or topic
        _set_thread(db, channel, {"topic": topic, "hook": hook, "by": names.get("A", "")})
        _remember_talk(db, cast, topic, hook)
        _mark_said(db, raw_lines)
    return n


def ambient(db: Session, persona: AiPersona, channel: str = "global") -> str:
    if in_pause(db, channel) or _queued(channel):
        return ""  # the channel is resting after a discussion, or a discussion is going on
    from . import chains
    ctx = _ctx(db)
    said = set(_said(db))
    text = chains.ambient_line(_rng, ctx, said)
    if not text:
        pool = AMBIENT.get(persona.style, []) + AMBIENT["any"]
        text = _fill(_rng.choice(pool), {}, ctx)
    _mark_said(db, [text])
    _queue.append((time.monotonic() + _rng.uniform(0, 5), persona.user_id, channel, text))
    return text


def flush(db: Session, limit: int = 20) -> int:
    """Posts queued lines whose time has come: at most one per channel per call and never sooner than the minimum gap
    after the previous AI message in that channel. When a channel's discussion is over, it goes quiet for a while."""
    now = time.monotonic()
    posted = 0
    keep = deque()
    gap = int(_speech(db).get("chat_min_gap_s", 10))
    done_in: set[str] = set()
    blocked: set[str] = set()
    while _queue:
        item = _queue.popleft()
        _, uid, channel, text = item
        if item[0] > now or posted >= limit or channel in done_in or channel in blocked:
            keep.append(item)
            continue
        if not channel.startswith("dm:") and _seconds_since_ai(db, channel) < gap:
            blocked.add(channel)  # keep the order of the discussion: the next line waits for the gap
            keep.append(item)
            continue
        if db.get(PlayerProfile, uid) is None:
            continue
        persona = db.scalar(select(AiPersona).where(AiPersona.user_id == uid))
        if persona is not None:  # each persona keeps its own manner of speech and mood (Living World AI stage 7)
            from ...ai import speech as SP
            text = _manner(persona, text)
            text = SP.stylize(_rng, persona, text, {**_speech(db), "length": "medium"})
        db.add(ChatMessage(channel=channel, user_id=uid, text=text[:300], is_ai=True, reactions={}))
        p = db.get(PlayerProfile, uid)
        p.last_seen_at = utcnow()
        posted += 1
        done_in.add(channel)
    _queue.extend(keep)
    for ch in done_in:
        if not ch.startswith("dm:") and not _queued(ch):
            _set_pause(db, ch)  # the discussion is over: a real chat goes quiet for a while
    db.flush()
    return posted


def _seconds_since_ai(db: Session, channel: str) -> float:
    last = db.scalar(select(func.max(ChatMessage.created_at)).where(ChatMessage.channel == channel,
                                                                     ChatMessage.is_ai.is_(True)))
    if last is None:
        return 1e9
    from ...core.db import as_utc
    return (utcnow() - as_utc(last)).total_seconds()


_speech_cache: dict = {"at": 0.0, "value": None}


def _speech(db: Session) -> dict:
    if _speech_cache["value"] is None or time.monotonic() - _speech_cache["at"] > 30:
        from ...ai import speech as SP
        _speech_cache.update(at=time.monotonic(), value=SP.SECTION.get(db))
    return _speech_cache["value"]


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
    from ...ai import speech as SP
    freq = SP.frequency(db)  # admin "chat frequency" scales the hourly AI chat budget
    from .. import channels as _CHN
    if pending == 0 and freq > 0 and _CHN.ai_may_post(db, "global") and \
            ai_messages_last_hour(db) < cfg.get("chat_ai_per_hour", 45) * freq:
        if minutes_since_last(db) >= 0.8 and not in_pause(db, "global"):
            if _rng.random() < 0.65:
                stats["started"] = start_conversation(db)
            else:
                p = db.scalars(select(AiPersona).where(AiPersona.active.is_(True)).order_by(func.random()).limit(1)).first()
                if p and ambient(db, p):
                    stats["started"] = 1
            _last_start = time.monotonic()
    from .. import channels as CHN
    # regional, event, alliance and group channels where a real player can read (Living World AI stage 8)
    if pending == 0 and freq > 0 and _rng.random() < cfg.get("extra_chat_chance", 0.3):
        stats["started"] += _extra_channel_talk(db)
    # guild chats: only guilds where real players can read; at most one conversation in progress overall
    if pending == 0 and _CHN.ai_may_post(db, "guild:x") and _rng.random() < cfg.get("guild_chat_chance", 0.25):
        from ...models import Guild
        humans = db.execute(select(GuildMember.guild_id).join(PlayerProfile, PlayerProfile.user_id == GuildMember.user_id)
                            .where(PlayerProfile.is_ai.is_(False))).scalars().all()
        for gid in set(humans):
            g = db.get(Guild, gid)
            if g is None or minutes_since_last(db, f"guild:{gid}") < cfg.get("guild_quiet_minutes", 20) or in_pause(db, f"guild:{gid}"):
                continue
            ids = [m.user_id for m in db.scalars(select(GuildMember).where(GuildMember.guild_id == gid))]
            members = db.scalars(select(AiPersona).where(AiPersona.user_id.in_(ids), AiPersona.active.is_(True))).all()
            if len(members) >= 2:
                stats["started"] += start_conversation(db, f"guild:{gid}", list(members))
                break
    return stats


def _extra_channel_talk(db: Session) -> int:
    from .. import channels as CHN
    from ...models import WorldEvent  # noqa: F401
    opts: list[tuple[str, list[AiPersona]]] = []
    st = CHN.SECTION.get(db)
    ev = CHN.active_event(db)
    if ev is not None and st["event_enabled"] and st["ai_event"]:
        ch = f"event:{ev.id}"
        if not in_pause(db, ch) and CHN.readers_online(db, ch):
            opts.append((ch, list(db.scalars(select(AiPersona).where(AiPersona.active.is_(True)).order_by(func.random()).limit(30)))))
    if st["region_enabled"] and st["ai_region"]:
        from ...models import PlayerCaravan
        from datetime import timedelta
        since = utcnow() - timedelta(minutes=15)
        locs = set(db.scalars(select(PlayerCaravan.location).join(PlayerProfile, PlayerProfile.user_id == PlayerCaravan.user_id)
                              .where(PlayerProfile.is_ai.is_(False), PlayerProfile.last_seen_at >= since)))
        for code in locs:
            ch = f"region:{code}"
            if in_pause(db, ch):
                continue
            locals_ = [p for p in db.scalars(select(AiPersona).where(AiPersona.active.is_(True)).limit(300)) if CHN.ai_region(p) == code]
            if len(locals_) >= 2:
                opts.append((ch, locals_))
    for kind in ("alliance", "group"):
        if not (st[f"{kind}_enabled"] and st[f"ai_{kind}"]):
            continue
        from ...models import AiSocialGroup, GuildAlliance
        rows = db.scalars(select(GuildAlliance).limit(20)) if kind == "alliance" else \
            db.scalars(select(AiSocialGroup).where(AiSocialGroup.active.is_(True)).limit(30))
        for r in rows:
            ch = f"{kind}:{r.id}"
            if in_pause(db, ch) or not CHN.readers_online(db, ch):
                continue
            ids = CHN.ai_member_ids(db, ch) or []
            ps = list(db.scalars(select(AiPersona).where(AiPersona.user_id.in_(ids), AiPersona.active.is_(True))))
            if len(ps) >= 2:
                opts.append((ch, ps))
    if not opts:
        return 0
    ch, cands = _rng.choice(opts)
    return start_conversation(db, ch, cands)


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
