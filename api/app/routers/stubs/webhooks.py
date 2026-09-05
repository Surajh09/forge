from fastapi import APIRouter, Header

from app.routers.stubs import not_implemented
from app.schemas import ClaudeWebhookEvent, NotImplementedOut

router = APIRouter(prefix="/webhooks", tags=["extension: event / webhook layer"])

_RESP = {501: {"model": NotImplementedOut}}


@router.post("/claude", responses=_RESP, summary="Claude session lifecycle events")
def claude_webhook(body: ClaudeWebhookEvent, x_forge_signature: str | None = Header(default=None)):
    # Webhooks are authenticated by signature, not by a user session.
    raise not_implemented(
        "Claude webhook ingestion is not part of the POC.",
        [
            "verify X-Forge-Signature",
            "dedupe by event_id (duplicate delivery is expected)",
            "map session_id → Forge session + authorization scope",
            "session.ended / session.compacted → enqueue context extraction",
        ],
    )


@router.post("/clerk", responses=_RESP, summary="Clerk user/organization events")
def clerk_webhook(svix_id: str | None = Header(default=None), svix_signature: str | None = Header(default=None)):
    raise not_implemented(
        "Clerk webhooks are not part of the POC; identities are upserted on first authenticated request.",
        [
            "verify Svix signature",
            "user.updated / organizationMembership.* → refresh users table",
            "organization.deleted → tenant offboarding",
        ],
    )
