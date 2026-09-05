from fastapi import APIRouter, Depends

from app.access import SCOPE_CONTEXT_READ, Principal
from app.auth import scoped
from app.repos import identity as identity_repo
from app.repos import teams as teams_repo
from app.repos import users as users_repo
from app.schemas import MeOut, OrganizationOut, PrincipalOut, TeamSummary, UserOut

router = APIRouter(tags=["identity"])


@router.get("/me", response_model=MeOut)
def me(p: Principal = Depends(scoped(SCOPE_CONTEXT_READ))) -> MeOut:
    org = identity_repo.get_org(p.org_id) or {"clerk_org_id": p.org_id, "name": p.org_id, "slug": None}
    user = users_repo.get_user(p.org_id, p.user_id) or {
        "id": p.user_id,
        "clerk_org_id": p.org_id,
        "display_name": p.user_id,
        "role": p.role,
    }
    my_team_ids = teams_repo.my_team_ids(p.org_id, p.user_id)
    teams = [TeamSummary.model_validate(t) for t in teams_repo.list_teams(p.org_id) if t["id"] in my_team_ids]
    return MeOut(
        principal=PrincipalOut(user_id=p.user_id, org_id=p.org_id, role=p.role, clerk_role=p.clerk_role),
        user=UserOut.model_validate(user),
        organization=OrganizationOut.model_validate(org),
        teams=teams,
    )
