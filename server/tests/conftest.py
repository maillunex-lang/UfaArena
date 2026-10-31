import os
import tempfile
import uuid
from pathlib import Path

import pytest

_tmp = Path(tempfile.mkdtemp(prefix="uralia-test-"))
os.environ.setdefault("URALIA_ENV", "test")
os.environ.setdefault("URALIA_DATABASE_URL", f"sqlite:///{_tmp / 'test.db'}")
os.environ["URALIA_CONTENT_SIGNING_KEY_PATH"] = str(_tmp / "sign.pem")
# The store must live as long as the DB: a persistent PostgreSQL test DB gets a persistent store.
_db = os.environ.get("URALIA_DATABASE_URL", "")
os.environ["URALIA_CONTENT_STORE_PATH"] = (
    str(Path(tempfile.gettempdir()) / ("uralia-test-store-" + __import__("hashlib").md5(_db.encode()).hexdigest()[:8]))
    if _db.startswith("postgresql") else str(_tmp / "store"))
os.environ["URALIA_RATE_LIMIT_PER_MINUTE"] = "100000"
os.environ["URALIA_AUTH_RATE_LIMIT_PER_MINUTE"] = "100000"

from fastapi.testclient import TestClient  # noqa: E402

from app.core import ratelimit  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_rl():
    ratelimit.reset()


class Player:
    def __init__(self, client):
        self.c = client
        r = client.post("/api/v1/auth/guest", json={"device_id": "test-" + uuid.uuid4().hex})
        assert r.status_code == 200, r.text
        self.tokens = r.json()

    @property
    def h(self):
        return {"Authorization": f"Bearer {self.tokens['access_token']}"}

    def get(self, path, **kw):
        return self.c.get("/api/v1" + path, headers=self.h, **kw)

    def post(self, path, json=None, key=None, **kw):
        h = dict(self.h)
        if key is not False:
            h["Idempotency-Key"] = key or uuid.uuid4().hex
        return self.c.post("/api/v1" + path, json=json, headers=h, **kw)


@pytest.fixture
def newplayer(client):
    return lambda: Player(client)
