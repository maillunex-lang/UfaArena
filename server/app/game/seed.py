"""Idempotent upsert of static content into the DB (run on startup and by `python -m app.game.seed`)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    CampaignNode, CampaignRegion, Faction, Hero, HeroClass,
    MailMessage, Quest, SummonPool,
)
from . import data as D


def seed_static(db: Session) -> None:
    for f in D.FACTIONS:
        db.merge(Faction(code=f["code"], name=f["name"], description=f.get("description", ""),
                         is_rare=f.get("is_rare", False), strong_against=f.get("strong_against"),
                         emblem=f.get("emblem", f["code"]), color=f.get("color", "#ffffff"),
                         accent=f.get("accent", "#ffffff"), playable=f["code"] != "shulgan"))
    for c in D.CLASSES:
        db.merge(HeroClass(**c))
    db.flush()
    for h in D.HEROES:
        db.merge(Hero(**{"title": "", "lore": "", "is_enemy": False, "summonable": True, "role": "", "kit": None,
                         "extra": {}, **h}))
    db.flush()
    # provisional 0.1 factions are retired once no hero references them (heroes were remapped above)
    from sqlalchemy import delete
    official = {f["code"] for f in D.FACTIONS}
    db.execute(delete(Faction).where(Faction.code.not_in(official)))
    for r in D.REGIONS:
        db.merge(CampaignRegion(**r))
    db.flush()
    for n in D.NODES:
        db.merge(CampaignNode(**{"region_code": "r1_shikhany", "is_boss": False, **n}))
    for p in D.SUMMON_POOLS:
        db.merge(SummonPool(**p))
    for q in D.QUESTS:
        db.merge(Quest(**{"requires": None, **q}))
    db.flush()
    from ..game_editor.overrides import apply as apply_admin_layer
    apply_admin_layer(db)  # admin edits (heroes, campaign, map) survive restarts and code updates
    if db.scalar(select(MailMessage).where(MailMessage.code == D.WELCOME_MAIL["code"])) is None:
        db.add(MailMessage(**D.WELCOME_MAIL))
    db.commit()
    from ..modules.content import ensure_initial
    from ..monetization import catalog as shop_catalog

    ensure_initial(db)
    shop_catalog.seed(db)
    db.commit()


if __name__ == "__main__":  # pragma: no cover
    from ..core.db import get_engine, init_engine
    from sqlalchemy.orm import Session as S

    init_engine()
    with S(get_engine()) as s:
        seed_static(s)
    print("seeded")
