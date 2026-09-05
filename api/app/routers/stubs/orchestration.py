from fastapi import APIRouter, Depends

from app.access import Principal
from app.auth import get_principal
from app.routers.stubs import not_implemented
from app.schemas import NotImplementedOut, OrchestrationRequest

router = APIRouter(prefix="/orchestration", tags=["extension: orchestration"])


@router.post("/sessions", responses={501: {"model": NotImplementedOut}}, summary="Launch an agent session")
def launch(body: OrchestrationRequest, p: Principal = Depends(get_principal)):
    raise not_implemented(
        "Orchestration Server is not part of the POC.",
        [
            "derive agent scope from the caller (user, org, team, feature, role)",
            "assemble relevant context from the Context Bank",
            "dispatch to the Local Agent Runtime in the customer environment",
            "track the session lifecycle via the Event / Webhook layer",
        ],
    )
