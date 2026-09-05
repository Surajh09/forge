"""Auth & Access Layer — Clerk session-token verification → Principal.

The UI calls this API server-to-server with `Authorization: Bearer <Clerk
session JWT>`. We verify it with the Clerk SDK (JWKS + `azp` check against the
UI origin), then read the organization claims:

  token v2: payload["o"] = {"id": "org_…", "rol": "admin", "slg": "…", …}
  token v1: payload["org_id"], payload["org_role"] = "org:admin"   (fallback)

A request without an active organization is rejected — every Forge resource
is tenant-scoped.
"""

from __future__ import annotations

import time
from threading import Lock

from clerk_backend_api.security.types import AuthenticateRequestOptions
from fastapi import Depends, HTTPException, Request, status

from app.access import Principal, normalize_role
from app.clerk import clerk_client
from app.config import get_settings
from app.repos import identity as identity_repo

# Clerk session tokens live ~60s; caching by raw token until `exp` avoids a
# JWKS round-trip on every request without weakening verification.
_token_cache: dict[str, tuple[float, Principal]] = {}
_token_cache_lock = Lock()


def _error(code: str, message: str, http_status: int) -> HTTPException:
    return HTTPException(status_code=http_status, detail={"code": code, "message": message})


def _org_claims(payload: dict) -> tuple[str | None, str | None]:
    o = payload.get("o")
    if isinstance(o, dict) and o.get("id"):
        return o["id"], o.get("rol")
    return payload.get("org_id"), payload.get("org_role")


def _cache_get(token: str) -> Principal | None:
    with _token_cache_lock:
        hit = _token_cache.get(token)
        if hit and hit[0] > time.time():
            return hit[1]
        if hit:
            del _token_cache[token]
    return None


def _cache_put(token: str, exp: float, principal: Principal) -> None:
    with _token_cache_lock:
        if len(_token_cache) > 5000:
            _token_cache.clear()
        _token_cache[token] = (exp, principal)


def get_principal(request: Request) -> Principal:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise _error("UNAUTHENTICATED", "Missing bearer token.", status.HTTP_401_UNAUTHORIZED)
    token = header.split(" ", 1)[1].strip()

    # Forge OAuth credentials are opaque and deliberately never sent to Clerk.
    # Keep their revocation checks live rather than placing them in the Clerk JWT
    # cache below.
    from app.oauth import ACCESS_PREFIX, principal_for_bearer

    if token.startswith(ACCESS_PREFIX):
        principal = principal_for_bearer(token)
        if not principal:
            raise _error("INVALID_TOKEN", "Agent credential is invalid, expired, or revoked.", status.HTTP_401_UNAUTHORIZED)
        return principal

    cached = _cache_get(token)
    if cached:
        return cached

    settings = get_settings()
    state = clerk_client().authenticate_request(
        request,
        AuthenticateRequestOptions(
            secret_key=settings.clerk_secret_key,
            authorized_parties=settings.authorized_parties,
        ),
    )
    if not state.is_signed_in or not state.payload:
        raise _error("INVALID_TOKEN", state.message or "Token verification failed.", status.HTTP_401_UNAUTHORIZED)

    payload = state.payload
    user_id = payload.get("sub")
    if not user_id:
        raise _error("INVALID_TOKEN", "Token has no subject.", status.HTTP_401_UNAUTHORIZED)

    org_id, clerk_role = _org_claims(payload)
    if not org_id:
        raise _error(
            "ORG_REQUIRED",
            "No active organization. Select or create an organization in Forge first.",
            status.HTTP_403_FORBIDDEN,
        )

    principal = Principal(
        user_id=user_id,
        org_id=org_id,
        role=normalize_role(clerk_role),
        clerk_role=clerk_role or "",
    )
    identity_repo.ensure_identity(principal)

    exp = float(payload.get("exp") or (time.time() + 30))
    _cache_put(token, min(exp, time.time() + 300), principal)
    return principal


def require_admin(p: Principal = Depends(get_principal)) -> Principal:
    if not p.is_admin:
        raise _error("ADMIN_REQUIRED", "This action requires the organization admin role.", status.HTTP_403_FORBIDDEN)
    return p


def scoped(scope: str):
    """Dependency factory: authenticate, then require an OAuth scope (phase-2 §14).

    Agent tokens are accepted on every route, so every route must declare the
    scope it needs. Users hold all scopes implicitly and are unaffected.
    """

    def dependency(p: Principal = Depends(get_principal)) -> Principal:
        if not p.has_scope(scope):
            raise _error("SCOPE_REQUIRED", f"This action requires the '{scope}' scope.", status.HTTP_403_FORBIDDEN)
        return p

    dependency.__name__ = f"scoped_{scope.replace('.', '_')}"
    return dependency
