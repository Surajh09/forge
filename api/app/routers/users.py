from fastapi import APIRouter, Depends

from app.access import SCOPE_CONTEXT_READ, Principal
from app.auth import scoped
from app.repos import users as users_repo
from app.schemas import UserOut

router = APIRouter(prefix="/users", tags=["identity"])


@router.get("", response_model=list[UserOut])
def list_users(p: Principal = Depends(scoped(SCOPE_CONTEXT_READ))) -> list[UserOut]:
    """Members of the caller's organization known to Forge (real + seeded demo users)."""
    return [UserOut.model_validate(u) for u in users_repo.list_users(p.org_id)]
