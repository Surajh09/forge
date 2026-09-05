"""Forge as an OAuth 2.1 authorization server for MCP (phase-2 §5).

The `mcp` SDK owns the protocol surface — /register, /authorize, /token,
/revoke, the RFC 8414 and RFC 9728 metadata documents, PKCE verification and
bearer-token middleware. This module supplies the provider behind it:

    Claude Code ──register──▶ oauth_clients
                ──authorize─▶ pending authorization ──▶ consent page in the web app
    user approves (Clerk-authenticated) ──▶ agent_grants row + authorization code
    Claude Code ──token──────▶ opaque access + refresh tokens bound to the grant
    Claude Code ──/mcp──────▶ bearer token ──▶ Principal(agent) for the tool call

The grant *is* the agent credential of §5.1: organization, creator, principal
type, scopes, optional feature allow-list, expiry, revocation, last use. The
agent only ever holds an opaque Forge token, never a Clerk secret or the
service-role key.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from mcp.server.auth.provider import AuthorizeError

from app import services
from app.access import AGENT_ROLE_CAP, ALL_SCOPES, Principal
from app.config import get_settings
from app.repos import oauth as repo
from app.repos import users as users_repo

ACCESS_TOKEN_TTL = timedelta(hours=1)
REFRESH_TOKEN_TTL = timedelta(days=30)
AUTH_CODE_TTL = timedelta(minutes=10)
PENDING_TTL = timedelta(minutes=15)
DEFAULT_GRANT_TTL = timedelta(days=90)

ACCESS_PREFIX = "forge_at_"
REFRESH_PREFIX = "forge_rt_"
CODE_PREFIX = "forge_ac_"


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _new_secret(prefix: str) -> str:
    return prefix + secrets.token_urlsafe(32)


def _parse_ts(value: str | None) -> float | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def _grant_is_live(grant: dict | None) -> bool:
    if not grant or grant.get("status") != "active":
        return False
    exp = _parse_ts(grant.get("expires_at"))
    return exp is None or exp > time.time()


def _validated_scopes(requested: list[str] | None) -> list[str]:
    """Validate the scopes an OAuth client asks for.

    An omitted scope means "the server's default" in OAuth, and clients such as
    Claude Code rely on that — so an empty request is widened to the full set
    rather than refused. Unknown scopes are still an error: a client asking for
    something Forge does not offer has misunderstood the server.

    This is the *requested* set, not the granted one. The human narrows it on
    the consent screen (`narrow_scopes`), which is where least privilege is
    actually applied.
    """
    scopes = list(dict.fromkeys(requested or []))
    if not scopes:
        return list(ALL_SCOPES)
    unknown = [scope for scope in scopes if scope not in ALL_SCOPES]
    if unknown:
        raise ValueError(f"Unsupported scope(s): {', '.join(unknown)}.")
    return scopes


def narrow_scopes(requested: list[str], approved: list[str] | None) -> list[str]:
    """What the human actually granted: never more than the client asked for."""
    if approved is None:
        return list(requested)
    granted = [s for s in dict.fromkeys(approved) if s in requested]
    if not granted:
        raise ValueError("Approve at least one scope, or deny the request.")
    return granted


def _validate_feature_restrictions(p: Principal, feature_ids: list[str] | None) -> list[str] | None:
    if feature_ids is None:
        return None
    checked = list(dict.fromkeys(feature_ids))
    for feature_id in checked:
        # load_feature is the existing, server-side feature access boundary.
        # It proves both tenant ownership and the creator's legitimate access.
        services.load_feature(p, feature_id)
    return checked


# --- consent (called by the web app after the user approves) -----------------


def pending_authorization(pending_id: str) -> dict | None:
    """What a client is asking for, for the consent page."""
    pending = repo.get_pending(pending_id)
    if not pending or pending.get("consumed_at"):
        return None
    if (_parse_ts(pending["expires_at"]) or 0) < time.time():
        return None
    client = repo.get_client(pending["client_id"])
    params = pending["params"]
    return {
        "id": pending["id"],
        "client_id": pending["client_id"],
        "client_name": (client or {}).get("client_name") or pending["client_id"],
        "scopes": params.get("scopes") or [],
        "redirect_uri": params.get("redirect_uri"),
        "expires_at": pending["expires_at"],
    }


def approve_consent(
    pending_id: str,
    p: Principal,
    *,
    feature_ids: list[str] | None,
    scopes: list[str] | None = None,
    expires_in: timedelta = DEFAULT_GRANT_TTL,
) -> str:
    """Create the grant and authorization code; return where to send the browser.

    `scopes` is what the human ticked; it can only narrow what the client asked
    for. `feature_ids` optionally confines the credential to specific features.
    """
    pending = repo.get_pending(pending_id)
    if not pending or pending.get("consumed_at") or (_parse_ts(pending["expires_at"]) or 0) < time.time():
        raise ValueError("This authorization request has expired. Start again from the agent.")
    client = repo.get_client(pending["client_id"])
    if not client:
        raise ValueError("Unknown OAuth client.")

    params = pending["params"]
    requested = _validated_scopes(params.get("scopes"))
    granted = narrow_scopes(requested, scopes)
    checked_feature_ids = _validate_feature_restrictions(p, feature_ids)

    # Claim before creating a grant/code. Conditional state transition prevents
    # two browser submits from both issuing usable credentials.
    pending = repo.consume_pending(pending_id)
    if not pending:
        raise ValueError("This authorization request has already been handled. Start again from the agent.")
    params = pending["params"]

    grant = repo.create_grant(
        p.org_id,
        user_id=p.user_id,
        client_id=client["client_id"],
        client_name=client.get("client_name"),
        scopes=granted,
        feature_ids=checked_feature_ids,
        expires_at=datetime.now(timezone.utc) + expires_in,
    )

    code = _new_secret(CODE_PREFIX)
    repo.save_code(
        _hash(code),
        {
            "client_id": client["client_id"],
            "grant_id": grant["id"],
            "redirect_uri": params["redirect_uri"],
            "redirect_uri_provided_explicitly": bool(params.get("redirect_uri_provided_explicitly", True)),
            "code_challenge": params["code_challenge"],
            "scopes": granted,
            "resource": params.get("resource"),
            "expires_at": (datetime.now(timezone.utc) + AUTH_CODE_TTL).isoformat(),
        },
    )
    return construct_redirect_uri(params["redirect_uri"], code=code, state=params.get("state"))


def deny_consent(pending_id: str) -> str:
    pending = repo.consume_pending(pending_id)
    if not pending:
        raise ValueError("This authorization request has already been handled.")
    params = pending["params"]
    return construct_redirect_uri(
        params["redirect_uri"], error="access_denied", error_description="The user declined.", state=params.get("state")
    )


# --- bearer verification (shared by MCP middleware and REST) ------------------


def load_access_token_sync(token: str) -> AccessToken | None:
    if not token.startswith(ACCESS_PREFIX):
        return None
    row = repo.get_token(_hash(token))
    if not row or row["kind"] != "access" or row.get("revoked_at"):
        return None
    exp = _parse_ts(row.get("expires_at"))
    if exp is not None and exp < time.time():
        return None
    grant = repo.get_grant(row["grant_id"])
    if not _grant_is_live(grant):
        return None

    repo.touch_token(row["token_hash"])
    repo.touch_grant(grant["id"])
    return AccessToken(
        token=token,
        client_id=row["client_id"],
        scopes=list(row["scopes"]),
        expires_at=int(exp) if exp else None,
        resource=None,
        subject=grant["id"],
        claims={
            "org_id": grant["clerk_org_id"],
            "user_id": grant["user_id"],
            "feature_ids": grant.get("feature_ids"),
            "client_name": grant.get("client_name"),
        },
    )


def principal_from_access_token(tok: AccessToken) -> Principal:
    """The agent acts as the grant's creator, capped and narrowed (§5.1, §14)."""
    claims = tok.claims or {}
    feature_ids = claims.get("feature_ids")
    return Principal(
        user_id=claims["user_id"],
        org_id=claims["org_id"],
        role=AGENT_ROLE_CAP,
        clerk_role="",
        principal_type="agent",
        scopes=frozenset(tok.scopes),
        feature_ids=frozenset(str(f) for f in feature_ids) if feature_ids is not None else None,
        credential_id=tok.subject,
        client_name=claims.get("client_name"),
    )


def principal_for_bearer(token: str) -> Principal | None:
    tok = load_access_token_sync(token)
    if not tok:
        return None
    p = principal_from_access_token(tok)
    # The creator must still exist in this org; otherwise the grant is orphaned.
    if not users_repo.get_user(p.org_id, p.user_id):
        return None
    return p


# --- the SDK provider -------------------------------------------------------


class ForgeOAuthProvider:
    """Implements mcp.server.auth.provider.OAuthAuthorizationServerProvider."""

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        row = repo.get_client(client_id)
        return OAuthClientInformationFull.model_validate(row["client_info"]) if row else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        repo.save_client(
            client_info.client_id,
            client_name=client_info.client_name,
            redirect_uris=[str(u) for u in (client_info.redirect_uris or [])],
            client_info=client_info.model_dump(mode="json", exclude_none=True),
        )

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        """Park the request and send the browser to the Forge consent page."""
        try:
            scopes = _validated_scopes(params.scopes)
        except ValueError as exc:
            raise AuthorizeError("invalid_scope", str(exc)) from exc
        pending = repo.create_pending(
            client.client_id,
            {
                "state": params.state,
                "scopes": scopes,
                "code_challenge": params.code_challenge,
                "redirect_uri": str(params.redirect_uri),
                "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
                "resource": params.resource,
            },
            datetime.now(timezone.utc) + PENDING_TTL,
        )
        # The consent page must live on one known origin — a preview URL would
        # not be where the user is signed in — so this uses the canonical one.
        return f"{get_settings().primary_web_origin}/agent/authorize?txn={pending['id']}"

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        row = repo.get_code(_hash(authorization_code))
        if not row or row["client_id"] != client.client_id or row.get("used_at"):
            return None
        exp = _parse_ts(row["expires_at"]) or 0
        if exp < time.time():
            return None
        return AuthorizationCode(
            code=authorization_code,
            scopes=list(row["scopes"]),
            expires_at=exp,
            client_id=row["client_id"],
            code_challenge=row["code_challenge"],
            redirect_uri=row["redirect_uri"],
            redirect_uri_provided_explicitly=bool(row.get("redirect_uri_provided_explicitly", True)),
            resource=row.get("resource"),
            subject=row["grant_id"],
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        claimed = repo.consume_code(_hash(authorization_code.code), client.client_id)
        if not claimed:
            raise TokenError("invalid_grant", "The authorization code has already been used.")
        exp = _parse_ts(claimed.get("expires_at")) or 0
        if exp < time.time():
            raise TokenError("invalid_grant", "The authorization code has expired.")
        grant = repo.get_grant(authorization_code.subject or "")
        if not _grant_is_live(grant):
            raise TokenError("invalid_grant", "The grant behind this code is no longer active.")
        scopes = [scope for scope in authorization_code.scopes if scope in set(grant["scopes"])]
        if not scopes:
            raise TokenError("invalid_scope", "The grant does not allow the requested scopes.")
        return self._issue_tokens(client.client_id, grant["id"], scopes)

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> RefreshToken | None:
        if not refresh_token.startswith(REFRESH_PREFIX):
            return None
        row = repo.get_token(_hash(refresh_token))
        if not row or row["kind"] != "refresh" or row["client_id"] != client.client_id or row.get("revoked_at"):
            return None
        exp = _parse_ts(row.get("expires_at"))
        if exp is not None and exp < time.time():
            return None
        if not _grant_is_live(repo.get_grant(row["grant_id"])):
            return None
        return RefreshToken(
            token=refresh_token,
            client_id=row["client_id"],
            scopes=list(row["scopes"]),
            expires_at=int(exp) if exp else None,
            subject=row["grant_id"],
        )

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]
    ) -> OAuthToken:
        grant = repo.get_grant(refresh_token.subject or "")
        if not _grant_is_live(grant):
            raise TokenError("invalid_grant", "The grant behind this refresh token is no longer active.")
        authorized = set(refresh_token.scopes) & set(grant["scopes"])
        requested = list(dict.fromkeys(scopes or refresh_token.scopes))
        if not requested or any(scope not in authorized for scope in requested):
            raise TokenError("invalid_scope", "Refresh tokens cannot expand their authorized scopes.")
        # Rotation: the old refresh token dies the moment it is used.
        repo.revoke_token(_hash(refresh_token.token))
        return self._issue_tokens(client.client_id, refresh_token.subject or "", requested)

    async def load_access_token(self, token: str) -> AccessToken | None:
        return load_access_token_sync(token)

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        repo.revoke_token(_hash(token.token))

    async def exchange_identity_assertion(self, client: OAuthClientInformationFull, params: Any) -> OAuthToken:
        raise TokenError("unsupported_grant_type", "Identity assertion is not supported.")

    # --- helpers ---

    def _issue_tokens(self, client_id: str, grant_id: str, scopes: list[str]) -> OAuthToken:
        now = datetime.now(timezone.utc)
        access = _new_secret(ACCESS_PREFIX)
        refresh = _new_secret(REFRESH_PREFIX)
        repo.save_token(
            _hash(access),
            {
                "kind": "access",
                "client_id": client_id,
                "grant_id": grant_id,
                "scopes": list(scopes),
                "expires_at": (now + ACCESS_TOKEN_TTL).isoformat(),
            },
        )
        repo.save_token(
            _hash(refresh),
            {
                "kind": "refresh",
                "client_id": client_id,
                "grant_id": grant_id,
                "scopes": list(scopes),
                "expires_at": (now + REFRESH_TOKEN_TTL).isoformat(),
            },
        )
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=int(ACCESS_TOKEN_TTL.total_seconds()),
            scope=" ".join(scopes),
            refresh_token=refresh,
        )
