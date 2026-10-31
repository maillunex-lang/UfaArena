"""RSA-SHA256 signing of content manifests. Only the PUBLIC key ships with the client."""
from __future__ import annotations

import base64
import json
from functools import lru_cache

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from .config import get_settings


@lru_cache
def _private_key():
    path = get_settings().content_signing_key_path
    if not path.exists():
        if get_settings().env in ("beta", "prod"):
            raise RuntimeError("content signing key missing")
        path.parent.mkdir(parents=True, exist_ok=True)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
        path.chmod(0o600)
    return serialization.load_pem_private_key(path.read_bytes(), password=None)


def public_key_pem() -> str:
    return _private_key().public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sign(obj) -> str:
    return base64.b64encode(_private_key().sign(canonical(obj), padding.PKCS1v15(), hashes.SHA256())).decode()


def verify(obj, signature_b64: str) -> bool:
    try:
        _private_key().public_key().verify(base64.b64decode(signature_b64), canonical(obj), padding.PKCS1v15(),
                                           hashes.SHA256())
        return True
    except Exception:
        return False
