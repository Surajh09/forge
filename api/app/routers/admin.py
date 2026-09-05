from fastapi import APIRouter, Depends

from app.access import Principal, normalize_role
from app.auth import require_admin
from app.clerk import fetch_org_memberships
from app.repos import users as users_repo
from app.schemas import SeedResult, SyncResult
from app.seed import run_seed

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/seed", response_model=SeedResult)
def seed(p: Principal = Depends(require_admin)) -> SeedResult:
    """Idempotent demo data for the caller's organization (teams, features, demo users, sessions, context)."""
    created = run_seed(p)
    return SeedResult(created=created, message="Demo data loaded for this organization.")


@router.post("/sync-members", response_model=SyncResult)
def sync_members(p: Principal = Depends(require_admin)) -> SyncResult:
    """Pull the organization's members from Clerk into Forge so they can be added to teams/features."""
    rows = []
    for m in fetch_org_memberships(p.org_id):
        rows.append(
            {
                "id": m["id"],
                "email": m["email"],
                "display_name": m["display_name"],
                "avatar_url": m["avatar_url"],
                "role": normalize_role(m["clerk_role"]),
                "is_demo": False,
            }
        )
    n = users_repo.upsert_users(p.org_id, rows)
    return SyncResult(synced=n, message=f"Synced {n} member(s) from Clerk.")
