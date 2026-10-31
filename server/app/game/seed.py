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
        db.merge(Faction(**{"is_rare": False, **f}))
    for c in D.CLASSES:
        db.merge(HeroClass(**c))
    db.flush()
    for h in D.HEROES:
        db.merge(Hero(**{"title": "", "lore": "", "is_enemy": False, "summonable": True, **h}))
    for r in D.REGIONS:
        db.merge(CampaignRegion(**r))
    db.flush()
    for n in D.NODES:
        db.merge(CampaignNode(region_code="r1_shikhany", **{"is_boss": False, **n}))
    for p in D.SUMMON_POOLS:
        db.merge(SummonPool(**p))
    for q in D.QUESTS:
        db.merge(Quest(**{"requires": None, **q}))
    if db.scalar(select(MailMessage).where(MailMessage.code == D.WELCOME_MAIL["code"])) is None:
        db.add(MailMessage(**D.WELCOME_MAIL))
    db.commit()
    from ..modules.content import ensure_initial

    ensure_initial(db)


if __name__ == "__main__":  # pragma: no cover
    from ..core.db import get_engine, init_engine
    from sqlalchemy.orm import Session as S

    init_engine()
    with S(get_engine()) as s:
        seed_static(s)
    print("seeded")
