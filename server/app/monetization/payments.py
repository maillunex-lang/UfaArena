"""Pluggable payment providers. The server is the only source of truth for purchases.

- TestProvider: simulates the full cycle (order -> confirmation -> grant -> journal), ONLY in test mode.
  Never contacts any payment system; no money moves.
- RuStoreProvider / GooglePlayProvider: adapter skeletons. They report "configured" only when their
  credentials exist AND a verified implementation is shipped. Server-side verification against the
  stores' APIs (RuStore Pay API / Google Play Developer API purchases.products.get,
  purchases.subscriptionsv2.get, RTDN notifications) requires the owner's store accounts and keys,
  which this project does not have — so they refuse to verify instead of pretending.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os

from ..core.config import get_settings


class PaymentError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class Provider:
    name = "base"
    implemented = False

    def configured(self) -> bool:
        return False

    def verify_purchase(self, order, payload: dict, test_mode: bool) -> str:
        """Returns the provider transaction id after server-side verification."""
        raise PaymentError("provider_not_configured", f"Провайдер {self.name} не настроен")

    def parse_notification(self, headers: dict, body: bytes) -> dict:
        raise PaymentError("provider_not_configured", f"Провайдер {self.name} не настроен")


def _test_secret() -> bytes:
    return hashlib.sha256(("uralia-test-payments:" + get_settings().jwt_secret).encode()).digest()


class TestProvider(Provider):
    name = "test"
    implemented = True

    def configured(self) -> bool:
        return True

    def verify_purchase(self, order, payload: dict, test_mode: bool) -> str:
        if not test_mode:
            raise PaymentError("test_disabled", "Тестовые покупки отключены в коммерческом режиме")
        return f"test-{order.id}"

    @staticmethod
    def sign(body: bytes) -> str:
        return hmac.new(_test_secret(), body, hashlib.sha256).hexdigest()

    def parse_notification(self, headers: dict, body: bytes) -> dict:
        sig = headers.get("x-uralia-test-signature", "")
        if not hmac.compare_digest(sig, self.sign(body)):
            raise PaymentError("bad_signature", "Неверная подпись уведомления")
        return json.loads(body)  # {"type": "refund", "provider_txn_id": "..."}


class RuStoreProvider(Provider):
    name = "rustore"
    ENV = ("URALIA_RUSTORE_APP_ID", "URALIA_RUSTORE_KEY_ID", "URALIA_RUSTORE_PRIVATE_KEY")

    def configured(self) -> bool:
        return self.implemented and all(os.environ.get(k) for k in self.ENV)


class GooglePlayProvider(Provider):
    name = "google_play"
    ENV = ("URALIA_GOOGLE_PACKAGE_NAME", "URALIA_GOOGLE_SERVICE_ACCOUNT_JSON")

    def configured(self) -> bool:
        return self.implemented and all(os.environ.get(k) for k in self.ENV)


PROVIDERS: dict[str, Provider] = {p.name: p for p in (TestProvider(), RuStoreProvider(), GooglePlayProvider())}


def configured_providers() -> list[str]:
    """Real providers usable in commercial mode (test provider never counts)."""
    return [n for n, p in PROVIDERS.items() if n != "test" and p.configured()]


def status() -> list[dict]:
    out = []
    for n, p in PROVIDERS.items():
        env = getattr(p, "ENV", ())
        out.append({"provider": n, "implemented": p.implemented, "configured": p.configured(),
                    "credentials_present": all(os.environ.get(k) for k in env) if env else True,
                    "required_env": list(env)})
    return out
