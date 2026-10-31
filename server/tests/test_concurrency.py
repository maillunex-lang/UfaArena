"""Double-reward protection under concurrent requests (meaningful on PostgreSQL row locks)."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

pg = os.environ.get("URALIA_DATABASE_URL", "").startswith("postgresql")


@pytest.mark.skipif(not pg, reason="needs PostgreSQL row-level locking")
def test_parallel_complete_grants_once(newplayer):
    p = newplayer()
    while True:
        b = p.post("/battles/validate", {"node_id": "1-1"}, key=False).json()
        if b["simulation"]["result"] == "victory":
            break

    def claim(_):
        return p.post("/campaign/1-1/complete", {"battle_id": b["battle_id"]}, key=uuid.uuid4().hex).status_code

    with ThreadPoolExecutor(8) as ex:
        codes = list(ex.map(claim, range(8)))
    assert codes.count(200) == 1, codes
    gold_tx = [t for t in p.get("/player/me").json()["wallet"].items()]
    assert gold_tx


@pytest.mark.skipif(not pg, reason="needs PostgreSQL row-level locking")
def test_parallel_afk_claim_once(newplayer):
    from datetime import timedelta

    from sqlalchemy.orm import Session

    from app.core.db import get_engine
    from app.models import PlayerProfile

    p = newplayer()
    with Session(get_engine()) as db:
        prof = db.get(PlayerProfile, p.tokens["user_id"])
        prof.afk_last_claim_at = prof.afk_last_claim_at - timedelta(hours=3)
        db.commit()
    with ThreadPoolExecutor(6) as ex:
        codes = list(ex.map(lambda _: p.post("/rewards/afk/claim").status_code, range(6)))
    assert codes.count(200) == 1, codes
