from fastapi import APIRouter, Depends

from app.access import Principal
from app.auth import get_principal
from app.routers.stubs import not_implemented
from app.schemas import ContextSyncPullRequest, ContextSyncPushRequest, NotImplementedOut

router = APIRouter(prefix="/context-sync", tags=["extension: context sync"])

_RESP = {501: {"model": NotImplementedOut}}


@router.post("/push", responses=_RESP, summary="Local Context Store → Cloud Context Bank")
def push(body: ContextSyncPushRequest, p: Principal = Depends(get_principal)):
    raise not_implemented(
        "Context Sync Service is not part of the POC.",
        [
            "authorize client scope (user, org, team, feature)",
            "dedupe by idempotency_key",
            "validate entries against the Context Contract",
            "normalize + conflict-detect against current feature context",
            "write to Context Bank with provenance",
            "return new feature version",
        ],
    )


@router.post("/pull", responses=_RESP, summary="Cache miss → fetch relevant context")
def pull(body: ContextSyncPullRequest, p: Principal = Depends(get_principal)):
    raise not_implemented(
        "Context Sync Service is not part of the POC.",
        [
            "filter features by caller's access",
            "metadata filter (feature, version, recency)",
            "semantic retrieval (future)",
            "return entries newer than since_version per feature",
        ],
    )
