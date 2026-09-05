from fastapi import APIRouter, Depends

from app.access import Principal
from app.auth import get_principal
from app.routers.stubs import not_implemented
from app.schemas import IngestionRequest, NotImplementedOut

router = APIRouter(prefix="/ingestion", tags=["extension: context ingestion"])


@router.post(
    "/sessions/{session_id}/context",
    responses={501: {"model": NotImplementedOut}},
    summary="Agent submits end-of-session context",
)
def ingest(session_id: str, body: IngestionRequest, p: Principal = Depends(get_principal)):
    raise not_implemented(
        "Context Ingestion (validate / normalize / quality) is not part of the POC. "
        "Use POST /sessions/{id}/complete for the manual path.",
        [
            "verify the agent acts within the initiating user's scope",
            "validate against the Context Contract",
            "normalize wording/structure across models",
            "quality score + conflict detection vs. trusted context",
            "quarantine contradictions instead of overwriting",
            "write accepted entries to the Context Bank with provenance",
        ],
    )
