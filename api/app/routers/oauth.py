"""Clerk-authenticated consent bridge and grant management for Forge's MCP OAuth server.

The MCP SDK owns the public OAuth protocol endpoints (/register, /authorize,
/token, /revoke, metadata). These JSON endpoints serve Forge's own web app:
the consent page after the SDK has parked a valid authorization request, and
the "connected agents" list where a user (or admin) revokes a grant (§5.1).
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.access import Principal
from app.audit import record_audit
from app.auth import get_principal
from app.oauth import approve_consent, deny_consent, pending_authorization
from app.repos import features as features_repo
from app.repos import oauth as oauth_repo
from app.repos import users as users_repo
from app.schemas import AgentGrantOut, FeatureSummary, PendingAuthorizationOut, UserOut

router = APIRouter(prefix="/oauth", tags=["agent OAuth consent"])


class ConsentDecision(BaseModel):
    feature_ids: list[str] | None = Field(
        default=None,
        description="Optional feature allow-list. Omit for the creator's ordinary feature access.",
    )
    scopes: list[str] | None = Field(
        default=None,
        description="Scopes the user approved. Can only narrow what the client requested; omit to grant all of them.",
    )


class ConsentRedirect(BaseModel):
    redirect_url: str


def _human_only(p: Principal) -> None:
    # An agent must never be able to mint or revoke credentials for itself.
    if p.is_agent:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "HUMAN_REQUIRED", "message": "Only a signed-in person can manage agent credentials."},
        )


def _pending_or_404(txn: str) -> dict:
    pending = pending_authorization(txn)
    if not pending:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "AUTHORIZATION_NOT_FOUND", "message": "Authorization request was not found or has expired."},
        )
    return pending


@router.get("/consents/{txn}", response_model=PendingAuthorizationOut)
def get_consent(txn: str, p: Principal = Depends(get_principal)) -> PendingAuthorizationOut:
    """Load a pending OAuth request for the signed-in human's consent screen."""
    _human_only(p)
    return PendingAuthorizationOut.model_validate(_pending_or_404(txn))


@router.post("/consents/{txn}/approve", response_model=ConsentRedirect)
def approve(txn: str, body: ConsentDecision, p: Principal = Depends(get_principal)) -> ConsentRedirect:
    _human_only(p)
    try:
        url = approve_consent(txn, p, feature_ids=body.feature_ids, scopes=body.scopes)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "CONSENT_INVALID", "message": str(exc)},
        ) from exc
    record_audit(
        p, "oauth.consent.approve", "ok",
        input_meta={"txn": txn, "restricted": body.feature_ids is not None, "scopes": ",".join(body.scopes or [])},
    )
    return ConsentRedirect(redirect_url=url)


@router.post("/consents/{txn}/deny", response_model=ConsentRedirect)
def deny(txn: str, p: Principal = Depends(get_principal)) -> ConsentRedirect:
    _human_only(p)
    try:
        url = deny_consent(txn)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "CONSENT_INVALID", "message": str(exc)},
        ) from exc
    record_audit(p, "oauth.consent.deny", "ok", input_meta={"txn": txn})
    return ConsentRedirect(redirect_url=url)


# --- connected agents (grants) -------------------------------------------------


def _grant_out(org_id: str, row: dict, users_map: dict[str, dict], features_map: dict[str, dict]) -> AgentGrantOut:
    g = AgentGrantOut.model_validate(row)
    creator = users_map.get(row["user_id"])
    g.creator = UserOut.model_validate(creator) if creator else None
    g.features = [
        FeatureSummary.model_validate(features_map[f]) for f in (row.get("feature_ids") or []) if f in features_map
    ]
    return g


@router.get("/grants", response_model=list[AgentGrantOut])
def list_grants(p: Principal = Depends(get_principal)) -> list[AgentGrantOut]:
    """The caller's agent credentials; admins see every grant in the organization."""
    _human_only(p)
    rows = oauth_repo.list_grants(p.org_id, user_id=None if p.is_admin else p.user_id)
    users_map = users_repo.users_by_id(p.org_id)
    features_map = {f["id"]: f for f in features_repo.list_features(p.org_id)}
    return [_grant_out(p.org_id, r, users_map, features_map) for r in rows]


@router.delete("/grants/{grant_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_grant(grant_id: str, p: Principal = Depends(get_principal)) -> Response:
    """Revoke a grant: every access and refresh token bound to it stops working immediately."""
    _human_only(p)
    grant = oauth_repo.get_grant(grant_id)
    if not grant or grant["clerk_org_id"] != p.org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "GRANT_NOT_FOUND", "message": "Agent credential not found."},
        )
    if grant["user_id"] != p.user_id and not p.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "GRANT_FORBIDDEN", "message": "Only the creator or an admin can revoke this credential."},
        )
    oauth_repo.revoke_grant(p.org_id, grant_id)
    record_audit(p, "oauth.grant.revoke", "ok", input_meta={"grant_id": grant_id, "client_name": grant.get("client_name")})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
