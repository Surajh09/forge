"""HTTP-boundary tests for the first Phase 2 OAuth + MCP read slice."""

from __future__ import annotations

import asyncio
import base64
import hashlib
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from mcp.server.auth.provider import AccessToken, AuthorizationCode, AuthorizeError, RefreshToken, TokenError
from mcp.shared.auth import OAuthClientInformationFull

from app import context_actions, oauth
from app.access import Principal
from app.auth import get_principal
from app.main import app


# The OAuth fake and `oauth_repo` fixture live in tests/conftest.py, shared with test_phase2_actions.py.


def _client(client_id="client_1") -> OAuthClientInformationFull:
    return OAuthClientInformationFull.model_validate(
        {
            "client_id": client_id,
            "client_name": "Forge test client",
            "redirect_uris": ["http://localhost:3001/callback"],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        }
    )


def _pkce() -> tuple[str, str]:
    verifier = "v" * 48
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


async def _pending(provider: oauth.ForgeOAuthProvider, client: OAuthClientInformationFull, scope="context.read") -> str:
    _verifier, challenge = _pkce()
    redirect = await provider.authorize(
        client,
        oauth.AuthorizationParams(
            state="state_1", scopes=scope.split() if scope else [], code_challenge=challenge,
            redirect_uri="http://localhost:3001/callback", redirect_uri_provided_explicitly=True,
            resource="http://localhost:8000/mcp",
        ),
    )
    return parse_qs(urlparse(redirect).query)["txn"][0]


def _approve(provider, repo, principal, *, feature_ids=None):
    client = _client()
    repo.save_client(client.client_id, client_name=client.client_name, redirect_uris=[str(u) for u in client.redirect_uris], client_info=client.model_dump(mode="json"))
    txn = asyncio.run(_pending(provider, client))
    callback = oauth.approve_consent(txn, principal, feature_ids=feature_ids)
    code = parse_qs(urlparse(callback).query)["code"][0]
    return client, code


def test_omitted_scope_falls_back_to_the_server_default(oauth_repo):
    """Regression: Claude Code omits `scope` and relies on the server default.

    Rejecting an empty request made every real connection fail with
    invalid_scope before the browser ever reached the consent page.
    """
    provider = oauth.ForgeOAuthProvider()
    client = _client()
    oauth_repo.save_client(client.client_id, client_name=client.client_name, redirect_uris=[], client_info=client.model_dump(mode="json"))
    txn = asyncio.run(_pending(provider, client, scope=""))
    assert oauth.pending_authorization(txn)["scopes"] == list(oauth.ALL_SCOPES)


def test_unknown_scopes_are_still_rejected(oauth_repo):
    provider = oauth.ForgeOAuthProvider()
    client = _client()
    oauth_repo.save_client(client.client_id, client_name=client.client_name, redirect_uris=[], client_info=client.model_dump(mode="json"))
    with pytest.raises(AuthorizeError) as unknown:
        asyncio.run(_pending(provider, client, scope="admin.everything"))
    assert unknown.value.error == "invalid_scope"


def test_consent_can_only_narrow_the_requested_scopes(oauth_repo, world):
    provider = oauth.ForgeOAuthProvider()
    client = _client()
    oauth_repo.save_client(client.client_id, client_name=client.client_name, redirect_uris=[], client_info=client.model_dump(mode="json"))

    # The human unticks everything except read, from a full-set request.
    txn = asyncio.run(_pending(provider, client, scope=" ".join(oauth.ALL_SCOPES)))
    oauth.approve_consent(txn, world["alice"], feature_ids=None, scopes=["context.read"])
    grant = next(iter(oauth_repo.grants.values()))
    assert grant["scopes"] == ["context.read"]

    # Ticking something the client never asked for does not add it.
    txn2 = asyncio.run(_pending(provider, client, scope="context.read"))
    oauth.approve_consent(txn2, world["alice"], feature_ids=None, scopes=["context.read", "context.write"])
    newest = [g for g in oauth_repo.grants.values() if g["id"] != grant["id"]][0]
    assert newest["scopes"] == ["context.read"]

    # Approving nothing is a mistake, not a silent no-privilege credential.
    txn3 = asyncio.run(_pending(provider, client, scope="context.read"))
    with pytest.raises(ValueError, match="at least one scope"):
        oauth.approve_consent(txn3, world["alice"], feature_ids=None, scopes=[])


def test_feature_restriction_must_be_real_and_accessible(oauth_repo, world):
    provider = oauth.ForgeOAuthProvider()
    client = _client()
    oauth_repo.save_client(client.client_id, client_name=client.client_name, redirect_uris=[], client_info=client.model_dump(mode="json"))
    txn = asyncio.run(_pending(provider, client))
    with pytest.raises(Exception):
        oauth.approve_consent(txn, world["alice"], feature_ids=[world["secret"]["id"]])
    assert oauth_repo.pending[txn]["consumed_at"] is None
    with pytest.raises(Exception):
        oauth.approve_consent(txn, world["alice"], feature_ids=["missing-feature"])
    assert oauth_repo.pending[txn]["consumed_at"] is None


def test_code_consumption_is_atomic_and_refresh_cannot_expand_scopes(oauth_repo, world):
    provider = oauth.ForgeOAuthProvider()
    client, code = _approve(provider, oauth_repo, world["alice"])
    loaded = asyncio.run(provider.load_authorization_code(client, code))
    assert loaded is not None

    async def exchange_twice():
        return await asyncio.gather(
            provider.exchange_authorization_code(client, loaded),
            provider.exchange_authorization_code(client, loaded),
            return_exceptions=True,
        )

    first, second = asyncio.run(exchange_twice())
    assert sum(not isinstance(value, Exception) for value in (first, second)) == 1
    assert any(isinstance(value, TokenError) and value.error == "invalid_grant" for value in (first, second))
    token = first if not isinstance(first, Exception) else second
    refresh = asyncio.run(provider.load_refresh_token(client, token.refresh_token))
    assert refresh is not None
    with pytest.raises(TokenError) as denied:
        asyncio.run(provider.exchange_refresh_token(client, refresh, ["context.write"]))
    assert denied.value.error == "invalid_scope"


def test_revoked_and_expired_agent_tokens_do_not_resolve(oauth_repo, world):
    provider = oauth.ForgeOAuthProvider()
    _client_info, code = _approve(provider, oauth_repo, world["alice"])
    code_hash = oauth._hash(code)
    row = oauth_repo.codes[code_hash]
    token = provider._issue_tokens(row["client_id"], row["grant_id"], ["context.read"])
    assert oauth.principal_for_bearer(token.access_token) is not None
    oauth_repo.revoke_token(oauth._hash(token.access_token))
    assert oauth.principal_for_bearer(token.access_token) is None
    expired = "forge_at_expired"
    oauth_repo.save_token(oauth._hash(expired), {"kind": "access", "client_id": row["client_id"], "grant_id": row["grant_id"], "scopes": ["context.read"], "expires_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()})
    assert oauth.principal_for_bearer(expired) is None


def test_http_oauth_consent_token_exchange_and_mcp_reads(oauth_repo, world, http):
    app.dependency_overrides[get_principal] = lambda: world["alice"]
    try:
        client = http
        registered = client.post(
            "/register",
            json={
                "client_name": "HTTP MCP client",
                "redirect_uris": ["http://localhost:3001/callback"],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
                "scope": "context.read",
            },
        )
        assert registered.status_code == 201
        client_info = registered.json()
        verifier, challenge = _pkce()
        authorize = client.get(
            "/authorize",
            params={
                "response_type": "code", "client_id": client_info["client_id"],
                "redirect_uri": "http://localhost:3001/callback", "code_challenge": challenge,
                "code_challenge_method": "S256", "scope": "context.read", "state": "state_1",
                "resource": "http://localhost:8000/mcp",
            },
            follow_redirects=False,
        )
        assert authorize.status_code in {302, 303, 307}
        txn = parse_qs(urlparse(authorize.headers["location"]).query)["txn"][0]
        pending = client.get(f"/api/v1/oauth/consents/{txn}")
        assert pending.status_code == 200
        approved = client.post(f"/api/v1/oauth/consents/{txn}/approve", json={"feature_ids": [world["payment"]["id"]]})
        assert approved.status_code == 200
        code = parse_qs(urlparse(approved.json()["redirect_url"]).query)["code"][0]
        token_response = client.post(
            "/token",
            data={
                "grant_type": "authorization_code", "code": code, "redirect_uri": "http://localhost:3001/callback",
                "client_id": client_info["client_id"], "code_verifier": verifier,
            },
        )
        assert token_response.status_code == 200
        access_token = token_response.json()["access_token"]

        # Make actual Phase 1 context available through the mounted MCP app.
        context_actions.record_context(
            world["alice"], world["payment"]["id"], kind="decision", title="Use idempotency keys",
            payload={"decision": "Use idempotency keys"}, confidence=0.9,
        )
        headers = {"authorization": f"Bearer {access_token}", "accept": "application/json"}
        initialized = client.post(
            "/mcp", headers=headers,
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}},
        )
        assert initialized.status_code == 200
        protocol = initialized.json()["result"]["protocolVersion"]
        headers["mcp-protocol-version"] = protocol
        feature = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "forge_feature_get", "arguments": {"feature": world["payment"]["id"]}}})
        assert feature.status_code == 200
        assert feature.json()["result"]["structuredContent"]["key"] == "PAYMENT"
        context = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "forge_context_get", "arguments": {"feature": world["payment"]["id"]}}})
        assert context.status_code == 200
        assert "Use idempotency keys" in context.json()["result"]["content"][0]["text"]
        denied = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "forge_context_get", "arguments": {"feature": world["login"]["id"]}}})
        assert denied.status_code == 200
        assert denied.json()["result"]["isError"] is True

        # A valid opaque credential without context.read reaches the MCP
        # transport but cannot invoke the read tool.
        code_row = oauth_repo.codes[oauth._hash(code)]
        scope_less = oauth.ForgeOAuthProvider()._issue_tokens(client_info["client_id"], code_row["grant_id"], [])
        no_scope_headers = {"authorization": f"Bearer {scope_less.access_token}", "accept": "application/json", "mcp-protocol-version": protocol}
        no_scope = client.post("/mcp", headers=no_scope_headers, json={"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "forge_context_get", "arguments": {"feature": world["payment"]["id"]}}})
        assert no_scope.json()["result"]["isError"] is True
        assert "context.read" in no_scope.json()["result"]["content"][0]["text"]
    finally:
        app.dependency_overrides.clear()
