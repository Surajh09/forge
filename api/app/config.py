from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_API_DIR = Path(__file__).resolve().parents[1]  # api/
_REPO_ROOT = _API_DIR.parent


class Settings(BaseSettings):
    """Runtime configuration for the Forge control plane.

    Loaded from the repo-root `.env` (shared Clerk keys) and then `api/.env`
    (Supabase etc.), later files winning; real environment variables win over both.
    """

    model_config = SettingsConfigDict(
        env_file=(str(_REPO_ROOT / ".env"), str(_API_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    clerk_secret_key: str
    # Comma-separated list of origins allowed as the `azp` claim of a Clerk session token.
    clerk_authorized_parties: str = "http://localhost:3000"

    supabase_url: str
    supabase_service_role_key: str

    # Origins of the Forge UI, comma-separated. The first is canonical and is
    # where the OAuth consent redirect goes; the rest are additional CORS
    # origins, which is how Vercel preview deployments (a new URL per deploy)
    # keep working without a redeploy of this service.
    web_origin: str = "http://localhost:3000"

    @property
    def web_origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.web_origin.split(",") if o.strip()]

    @property
    def primary_web_origin(self) -> str:
        return self.web_origins[0] if self.web_origins else "http://localhost:3000"

    # Public base URL of this API. It is the OAuth issuer and the base of the
    # MCP resource URL (`<forge_public_url>/mcp`) that agents connect to.
    forge_public_url: str = "http://localhost:8000"

    @property
    def mcp_resource_url(self) -> str:
        return self.forge_public_url.rstrip("/") + "/mcp"

    @property
    def authorized_parties(self) -> list[str]:
        return [p.strip() for p in self.clerk_authorized_parties.split(",") if p.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
