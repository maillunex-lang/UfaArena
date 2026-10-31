"""Runtime configuration. All secrets come from the environment, never from the client."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

SERVER_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="URALIA_", env_file=".env", extra="ignore")

    env: str = "dev"  # dev | test | beta | prod
    database_url: str = f"sqlite:///{SERVER_ROOT / 'var' / 'uralia.db'}"
    redis_url: str | None = None

    # JWT signing secret for short-lived access tokens. MUST be overridden outside dev.
    jwt_secret: str = "dev-only-insecure-secret-change-me-0123456789"
    access_token_ttl_s: int = 15 * 60
    refresh_token_ttl_s: int = 60 * 60 * 24 * 60

    # Content manifest signing key (RSA, PEM). Generated on first start in dev.
    content_signing_key_path: Path = SERVER_ROOT / "keys" / "content_signing.pem"
    content_channel: str = "dev"
    content_store_path: Path = SERVER_ROOT / "var" / "content_store"
    # Optional CDN prefix for package files, e.g. "https://cdn.example.com/uralia/" (files keyed by sha256)
    content_base_url: str | None = None

    rate_limit_per_minute: int = 120
    auth_rate_limit_per_minute: int = 20

    afk_max_hours_base: int = 8
    afk_min_claim_interval_s: int = 60

    def validate_for_env(self) -> None:
        if self.env in ("beta", "prod") and self.jwt_secret.startswith("dev-only"):
            raise RuntimeError("URALIA_JWT_SECRET must be set for beta/prod")


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.validate_for_env()
    return s
