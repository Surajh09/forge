"""Agent-facing Context Bank actions, served as TOON.

Same five actions as `app.context_actions`, same authorization, but the response
is TOON rather than JSON because these responses are meant to be dropped into a
model's context window (directive item 5).

Reads return `text/plain` TOON documents. Writes accept JSON (an agent posting a
statement is an ordinary API call) and return the resulting entry as TOON so the
agent immediately sees the stored version and its provenance.
"""

from fastapi import APIRouter, Body, Depends, Query, Response, status as http_status
from pydantic import BaseModel, Field

from app import context_actions, services
from app.access import Principal
from app.auth import get_principal
from app.schemas import ContextKind
from app.toon_codec import TOON_MEDIA_TYPE, entries_to_toon_document

router = APIRouter(prefix="/agent/context", tags=["context bank: agent actions"])

_TOON_RESPONSE = {
    200: {
        "content": {"text/plain": {"schema": {"type": "string"}}},
        "description": "TOON-encoded context document",
    }
}


def _toon(payload: dict, rows: list[dict], status_code: int = http_status.HTTP_200_OK) -> Response:
    doc = entries_to_toon_document(rows, feature=payload.get("feature"), query=payload.get("query"))
    return Response(content=doc, media_type=TOON_MEDIA_TYPE, status_code=status_code)


@router.get("/features/{feature_id}", responses=_TOON_RESPONSE, summary="get_feature_context")
def get_feature_context(feature_id: str, p: Principal = Depends(get_principal)) -> Response:
    """Active context for a feature, as TOON."""
    payload, rows = context_actions.get_feature_context(p, feature_id)
    return _toon(payload, rows)


@router.get("/features/{feature_id}/kinds", responses=_TOON_RESPONSE, summary="get_context_by_kind")
def get_context_by_kind(
    feature_id: str,
    kind: list[ContextKind] = Query(..., description="One or more context kinds"),
    p: Principal = Depends(get_principal),
) -> Response:
    """Active context for a feature filtered by kind, as TOON."""
    payload, rows = context_actions.get_context_by_kind(p, feature_id, list(kind))
    return _toon(payload, rows)


@router.get("/search", responses=_TOON_RESPONSE, summary="search_context")
def search_context(
    q: str = Query(..., min_length=2, description="Text to match in titles and payloads"),
    feature_id: str | None = Query(default=None),
    kind: list[ContextKind] | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    p: Principal = Depends(get_principal),
) -> Response:
    """Text search across features the caller may access, as TOON."""
    payload, rows = context_actions.search_context(
        p, q, feature_id=feature_id, kinds=list(kind) if kind else None, limit=limit
    )
    return _toon(payload, rows)


class RecordContextRequest(BaseModel):
    kind: ContextKind
    title: str = Field(min_length=1, max_length=500)
    payload: dict = Field(default_factory=dict)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    session_id: str | None = Field(default=None, description="Provenance: the session this came from")


@router.post(
    "/features/{feature_id}",
    responses=_TOON_RESPONSE,
    status_code=http_status.HTTP_201_CREATED,
    summary="record_context",
)
def record_context(
    feature_id: str,
    body: RecordContextRequest = Body(...),
    p: Principal = Depends(get_principal),
) -> Response:
    """Record one new statement; returns the stored entry as TOON."""
    created = context_actions.record_context(
        p,
        feature_id,
        kind=body.kind,
        title=body.title,
        payload=body.payload,
        confidence=body.confidence,
        session_id=body.session_id,
    )
    feature = services.load_feature(p, feature_id).feature
    return _toon({"feature": feature, "query": {"action": "record_context"}}, [created], http_status.HTTP_201_CREATED)


class SupersedeContextRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    payload: dict = Field(default_factory=dict)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    session_id: str | None = Field(default=None, description="Session that produced the replacement")


@router.post("/entries/{entry_id}/supersede", responses=_TOON_RESPONSE, summary="supersede_context")
def supersede_context(
    entry_id: str,
    body: SupersedeContextRequest = Body(...),
    p: Principal = Depends(get_principal),
) -> Response:
    """Replace a statement with a newer version; the old row is kept (§10)."""
    created = context_actions.supersede_context(
        p,
        entry_id,
        title=body.title,
        payload=body.payload,
        confidence=body.confidence,
        session_id=body.session_id,
    )
    return _toon({"query": {"action": "supersede_context", "superseded": entry_id}}, [created])
