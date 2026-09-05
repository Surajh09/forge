from functools import lru_cache

from clerk_backend_api import Clerk

from app.config import get_settings


@lru_cache
def clerk_client() -> Clerk:
    return Clerk(bearer_auth=get_settings().clerk_secret_key)


def fetch_user_profile(user_id: str) -> dict:
    """Best-effort profile lookup from the Clerk Backend API."""
    try:
        u = clerk_client().users.get(user_id=user_id)
    except Exception:  # noqa: BLE001 — degrade to an id-only profile
        return {"email": None, "display_name": user_id, "avatar_url": None}

    email = None
    for e in u.email_addresses or []:
        if e.id == u.primary_email_address_id:
            email = e.email_address
            break
    if email is None and u.email_addresses:
        email = u.email_addresses[0].email_address

    name = " ".join(p for p in [u.first_name, u.last_name] if p).strip()
    return {
        "email": email,
        "display_name": name or u.username or email or user_id,
        "avatar_url": u.image_url,
    }


def fetch_org_profile(org_id: str) -> dict:
    try:
        o = clerk_client().organizations.get(organization_id=org_id)
        return {"name": o.name, "slug": o.slug}
    except Exception:  # noqa: BLE001
        return {"name": org_id, "slug": None}


def fetch_org_memberships(org_id: str) -> list[dict]:
    """All members of a Clerk organization as flat dicts (paged, 100 at a time)."""
    out: list[dict] = []
    offset = 0
    while True:
        page = clerk_client().organization_memberships.list(organization_id=org_id, limit=100, offset=offset)
        for m in page.data or []:
            pud = m.public_user_data
            if not pud or not pud.user_id:
                continue
            name = " ".join(p for p in [pud.first_name, pud.last_name] if p).strip()
            out.append(
                {
                    "id": pud.user_id,
                    "email": pud.identifier,
                    "display_name": name or pud.username or pud.identifier or pud.user_id,
                    "avatar_url": pud.image_url,
                    "clerk_role": m.role,
                }
            )
        if len(page.data or []) < 100:
            return out
        offset += 100
