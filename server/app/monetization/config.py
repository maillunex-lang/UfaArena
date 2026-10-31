"""Monetization configuration (server-side only; the client never holds prices or rewards)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "game" / "content" / "monetization.json"


@lru_cache
def cfg() -> dict:
    return json.loads(PATH.read_text(encoding="utf-8"))


def cosmetic(cid: str) -> dict | None:
    for c in cfg()["cosmetics"]:
        if c["id"] == cid:
            return c
    return None


def rub(kopecks: int) -> str:
    v = kopecks / 100
    return f"{v:,.0f} ₽".replace(",", " ") if v == int(v) else f"{v:,.2f} ₽".replace(",", " ")
