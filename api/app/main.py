"""Forge Cloud Control Plane — FastAPI entrypoint.

Boxes from system-design.png → modules:
  API Gateway            → this app (/api/v1)
  Auth & Access Layer    → app/auth.py + app/access.py
  Feature Service        → routers/features.py
  Session Service        → routers/sessions.py
  Context Service        → routers/features.py (/context) + services.complete_session
  Forge Database /
  Cloud Context Bank     → Supabase Postgres (supabase/migrations)
  Context Sync Service   → routers/sync.py (Local Context Store ↔ cloud)
  Forge MCP              → app/mcp_server.py, mounted at /mcp
  Context Ingestion,
  Event / Webhook Layer,
  Orchestration Server   → routers/stubs/* (501, contracts only)
"""

from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from postgrest.exceptions import APIError

from app.config import get_settings
from app.routers import admin, agent, context, features, me, oauth, sessions, sync, teams, users
from app.routers.stubs import ingestion, orchestration, webhooks
from app.toon_codec import ToonError

settings = get_settings()

app = FastAPI(
    title="Forge API",
    version="0.1.0",
    description=(
        "Control plane for Forge: Clerk-authenticated, organization-scoped features, sessions and the "
        "Context Bank. Endpoints tagged *extension* document the non-POC pipeline and return 501."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.web_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(APIError)
def _db_error(_: Request, exc: APIError) -> JSONResponse:
    # Surface Postgres/PostgREST errors in the same {code, message} envelope as our own.
    return JSONResponse(status_code=500, content={"detail": {"code": "DB_ERROR", "message": exc.message}})


@app.exception_handler(ToonError)
def _toon_error(_: Request, exc: ToonError) -> JSONResponse:
    # Malformed context payloads are a client/data problem, not a server fault.
    return JSONResponse(
        status_code=422, content={"detail": {"code": "CONTEXT_MALFORMED", "message": str(exc)}}
    )


@app.get("/health", tags=["ops"])
def health() -> dict:
    return {"status": "ok"}


api = APIRouter(prefix="/api/v1")
api.include_router(me.router)
api.include_router(users.router)
api.include_router(teams.router)
api.include_router(features.router)
api.include_router(context.feature_router)
api.include_router(context.router)
api.include_router(agent.router)
api.include_router(sessions.router)
api.include_router(admin.router)
api.include_router(sync.router)
api.include_router(oauth.router)
api.include_router(ingestion.router)
api.include_router(webhooks.router)
api.include_router(orchestration.router)
app.include_router(api)


@app.api_route("/api/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
def _api_not_found(path: str) -> JSONResponse:
    # The MCP app is mounted at "/" as a fallback; without this, an unknown API
    # path would fall through to it and lose Forge's {code, message} envelope.
    return JSONResponse(status_code=404, content={"detail": {"code": "NOT_FOUND", "message": f"No route /api/v1/{path}"}})

# MCP owns its JSON-RPC wire format and OAuth protocol routes.  It is mounted
# after Forge's REST API so existing Phase 1 paths keep their routing surface.
from app.mcp_server import build_mcp_server  # noqa: E402

_mcp_server = build_mcp_server()
_mcp_app = _mcp_server.streamable_http_app(
    streamable_http_path="/mcp",
    json_response=True,
    stateless_http=True,
    host=urlparse(settings.forge_public_url).hostname or "localhost",
)


@asynccontextmanager
async def _mcp_lifespan(_: FastAPI):
    # Starlette does not automatically enter a mounted sub-application's
    # lifespan. The SDK's streamable HTTP manager must be running before it can
    # dispatch `/mcp` requests.
    async with _mcp_server.session_manager.run():
        yield


app.router.lifespan_context = _mcp_lifespan
app.mount(
    "/",
    _mcp_app,
)
