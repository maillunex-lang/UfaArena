"""Idempotent upsert of static content into the DB (run on startup and by `python -m app.game.seed`)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    CampaignNode, CampaignRegion, ContentManifestVersion, ContentPackage, Faction, Hero, HeroClass,
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
    db.merge(ContentPackage(package_id="core.balance", kind="balance", description="Баланс и данные героев"))
    db.merge(ContentPackage(package_id="core.l10n.ru", kind="l10n", description="Русская локализация"))
    db.flush()
    if db.scalar(select(ContentManifestVersion).where(ContentManifestVersion.channel == "dev")) is None:
        from ..modules.content import build_balance_package

        pkg = build_balance_package()
        db.add(ContentManifestVersion(channel="dev", platform="android", version=1, minimum_client_version="0.1.0",
                                      packages=[pkg], is_active=True))
    db.commit()


if __name__ == "__main__":  # pragma: no cover
    from ..core.db import get_engine, init_engine
    from sqlalchemy.orm import Session as S

    init_engine()
    with S(get_engine()) as s:
        seed_static(s)
    print("seeded")
