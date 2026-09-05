from fastapi import APIRouter, Depends, Response, status

from app.access import SCOPE_CONTEXT_READ, Principal
from app.auth import require_admin, scoped
from app.repos import teams as teams_repo
from app.repos import users as users_repo
from app.schemas import TeamCreate, TeamOut, TeamUpdate
from app.services import err, teams_with_members

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("", response_model=list[TeamOut])
def list_teams(p: Principal = Depends(scoped(SCOPE_CONTEXT_READ))) -> list[TeamOut]:
    return teams_with_members(p.org_id)


@router.post("", response_model=TeamOut, status_code=status.HTTP_201_CREATED)
def create_team(body: TeamCreate, p: Principal = Depends(require_admin)) -> TeamOut:
    if teams_repo.get_team_by_name(p.org_id, body.name):
        raise err("TEAM_EXISTS", f"A team named '{body.name}' already exists.", status.HTTP_409_CONFLICT)
    row = teams_repo.create_team(p.org_id, body.model_dump())
    return TeamOut.model_validate(row)


@router.patch("/{team_id}", response_model=TeamOut)
def update_team(team_id: str, body: TeamUpdate, p: Principal = Depends(require_admin)) -> TeamOut:
    data = body.model_dump(exclude_unset=True)
    row = teams_repo.update_team(p.org_id, team_id, data) if data else teams_repo.get_team(p.org_id, team_id)
    if not row:
        raise err("TEAM_NOT_FOUND", "Team not found.", status.HTTP_404_NOT_FOUND)
    return next(t for t in teams_with_members(p.org_id) if t.id == team_id)


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_team(team_id: str, p: Principal = Depends(require_admin)) -> Response:
    if not teams_repo.delete_team(p.org_id, team_id):
        raise err("TEAM_NOT_FOUND", "Team not found.", status.HTTP_404_NOT_FOUND)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{team_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def add_member(team_id: str, user_id: str, p: Principal = Depends(require_admin)) -> Response:
    if not teams_repo.get_team(p.org_id, team_id):
        raise err("TEAM_NOT_FOUND", "Team not found.", status.HTTP_404_NOT_FOUND)
    if not users_repo.get_user(p.org_id, user_id):
        raise err("USER_NOT_FOUND", "User is not a member of this organization in Forge.", status.HTTP_404_NOT_FOUND)
    teams_repo.add_member(p.org_id, team_id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{team_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(team_id: str, user_id: str, p: Principal = Depends(require_admin)) -> Response:
    teams_repo.remove_member(p.org_id, team_id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
