from fastapi import APIRouter, Depends, Response, status

from app.access import SCOPE_CONTEXT_READ, Principal
from app.auth import require_admin, scoped
from app.repos import features as features_repo
from app.repos import teams as teams_repo
from app.repos import users as users_repo
from app.schemas import FeatureCreate, FeatureDetail, FeatureOut, FeatureUpdate
from app.services import accessible_features, err, feature_detail

router = APIRouter(prefix="/features", tags=["features"])


@router.get("", response_model=list[FeatureOut])
def list_features(p: Principal = Depends(scoped(SCOPE_CONTEXT_READ))) -> list[FeatureOut]:
    """Features the caller may access (admin: all; else assigned or via a team)."""
    return accessible_features(p)


@router.post("", response_model=FeatureDetail, status_code=status.HTTP_201_CREATED)
def create_feature(body: FeatureCreate, p: Principal = Depends(require_admin)) -> FeatureDetail:
    if features_repo.get_feature_by_key(p.org_id, body.key):
        raise err("FEATURE_EXISTS", f"Feature key '{body.key}' already exists.", status.HTTP_409_CONFLICT)
    row = features_repo.create_feature(
        p.org_id,
        {"key": body.key, "name": body.name, "description": body.description},
        created_by=p.user_id,
    )
    for team_id in body.team_ids:
        if teams_repo.get_team(p.org_id, team_id):
            features_repo.add_team(p.org_id, row["id"], team_id)
    for user_id in body.assignee_ids:
        if users_repo.get_user(p.org_id, user_id):
            features_repo.add_assignee(p.org_id, row["id"], user_id)
    return feature_detail(p, row["id"])


@router.get("/{feature_id}", response_model=FeatureDetail)
def get_feature(feature_id: str, p: Principal = Depends(scoped(SCOPE_CONTEXT_READ))) -> FeatureDetail:
    """Feature + teams + assignees + the sessions and context the caller may see."""
    return feature_detail(p, feature_id)


@router.patch("/{feature_id}", response_model=FeatureDetail)
def update_feature(feature_id: str, body: FeatureUpdate, p: Principal = Depends(require_admin)) -> FeatureDetail:
    data = body.model_dump(exclude_unset=True)
    if data and not features_repo.update_feature(p.org_id, feature_id, data):
        raise err("FEATURE_NOT_FOUND", "Feature not found.", status.HTTP_404_NOT_FOUND)
    return feature_detail(p, feature_id)


@router.delete("/{feature_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_feature(feature_id: str, p: Principal = Depends(require_admin)) -> Response:
    if not features_repo.delete_feature(p.org_id, feature_id):
        raise err("FEATURE_NOT_FOUND", "Feature not found.", status.HTTP_404_NOT_FOUND)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Feature context lives in routers/context.py (feature_router) so the Context
# Bank surface is in one place.


# --- ownership links (admin) -------------------------------------------------


@router.post("/{feature_id}/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
def add_feature_team(feature_id: str, team_id: str, p: Principal = Depends(require_admin)) -> Response:
    if not features_repo.get_feature(p.org_id, feature_id):
        raise err("FEATURE_NOT_FOUND", "Feature not found.", status.HTTP_404_NOT_FOUND)
    if not teams_repo.get_team(p.org_id, team_id):
        raise err("TEAM_NOT_FOUND", "Team not found.", status.HTTP_404_NOT_FOUND)
    features_repo.add_team(p.org_id, feature_id, team_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{feature_id}/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_feature_team(feature_id: str, team_id: str, p: Principal = Depends(require_admin)) -> Response:
    features_repo.remove_team(p.org_id, feature_id, team_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{feature_id}/assignees/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def add_assignee(feature_id: str, user_id: str, p: Principal = Depends(require_admin)) -> Response:
    if not features_repo.get_feature(p.org_id, feature_id):
        raise err("FEATURE_NOT_FOUND", "Feature not found.", status.HTTP_404_NOT_FOUND)
    if not users_repo.get_user(p.org_id, user_id):
        raise err("USER_NOT_FOUND", "User is not a member of this organization in Forge.", status.HTTP_404_NOT_FOUND)
    features_repo.add_assignee(p.org_id, feature_id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{feature_id}/assignees/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_assignee(feature_id: str, user_id: str, p: Principal = Depends(require_admin)) -> Response:
    features_repo.remove_assignee(p.org_id, feature_id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
