from fastapi import APIRouter, Depends, Query, Response, status

from app.access import SCOPE_CONTEXT_READ, SCOPE_SESSION_WRITE, Principal, can_edit_session
from app.audit import record_audit
from app.auth import scoped
from app.repos import context as context_repo
from app.repos import sessions as sessions_repo
from app.schemas import (
    CompletionResult,
    ContextEntryOut,
    SessionCheckpoint,
    SessionComplete,
    SessionCreate,
    SessionOut,
    SessionUpdate,
)
from app.services import (
    checkpoint_session,
    complete_session,
    entry_out,
    err,
    feature_sessions,
    load_feature,
    load_visible_session,
    my_sessions,
    now_iso,
    session_with_context,
    start_session,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])

# Every route declares its scope (phase-2 §14). Users hold all scopes implicitly.
read = Depends(scoped(SCOPE_CONTEXT_READ))
write = Depends(scoped(SCOPE_SESSION_WRITE))


@router.get("", response_model=list[SessionOut])
def list_sessions(
    feature_id: str | None = Query(default=None),
    p: Principal = read,
) -> list[SessionOut]:
    """With feature_id: sessions on that feature visible to the caller. Without: the caller's own sessions."""
    if feature_id:
        sessions, _hidden = feature_sessions(p, load_feature(p, feature_id))
        return sessions
    return my_sessions(p)


@router.get("/mine", response_model=list[SessionOut])
def list_my_sessions(p: Principal = read) -> list[SessionOut]:
    return my_sessions(p)


@router.post("", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def create_session(body: SessionCreate, p: Principal = write) -> SessionOut:
    """Anyone with access to the feature may start a session on it; the author is always the caller."""
    row = start_session(p, body.feature_id, agent=body.agent, model=body.model, goal=body.goal)
    return session_with_context(p, row, "own")


@router.get("/{session_id}", response_model=SessionOut)
def get_session(session_id: str, p: Principal = read) -> SessionOut:
    row, reason, _ctx = load_visible_session(p, session_id)
    return session_with_context(p, row, reason)


@router.patch("/{session_id}", response_model=SessionOut)
def update_session(session_id: str, body: SessionUpdate, p: Principal = write) -> SessionOut:
    row, reason, _ctx = load_visible_session(p, session_id)
    if not can_edit_session(p, row):
        raise err("SESSION_READ_ONLY", "Only the session author or an admin can edit it.", status.HTTP_403_FORBIDDEN)
    data = body.model_dump(exclude_unset=True)
    if data.get("status") in {"completed", "failed", "abandoned"} and not row.get("ended_at"):
        data["ended_at"] = now_iso()
    updated = sessions_repo.update_session(p.org_id, session_id, data) if data else row
    return session_with_context(p, updated or row, reason)


@router.post("/{session_id}/checkpoint", response_model=CompletionResult)
def checkpoint(session_id: str, body: SessionCheckpoint, p: Principal = write) -> CompletionResult:
    """Preserve durable context mid-session (phase-2 §13.3). The session stays active.

    Supply `context` to use an authored contract, or omit it and the Context
    Generator derives one from session metadata. Idempotent by `request_id`.
    """
    row, _reason, _ctx = load_visible_session(p, session_id)
    if not can_edit_session(p, row):
        raise err("SESSION_READ_ONLY", "Only the session author or an admin can checkpoint it.", status.HTTP_403_FORBIDDEN)
    return checkpoint_session(p, row, body)


@router.post("/{session_id}/complete", response_model=CompletionResult)
def complete(session_id: str, body: SessionComplete, p: Principal = write) -> CompletionResult:
    """End a session: generate → validate → fan out into typed Context Bank entries.

    Supply `context` to use an authored contract, or omit it and the Context
    Generator derives one from session metadata. Idempotent: completing an
    already-completed session returns the entries written the first time.
    """
    row, _reason, _ctx = load_visible_session(p, session_id)
    if not can_edit_session(p, row):
        raise err("SESSION_READ_ONLY", "Only the session author or an admin can complete it.", status.HTTP_403_FORBIDDEN)
    return complete_session(p, row, body)


@router.get("/{session_id}/context", response_model=list[ContextEntryOut])
def session_context(session_id: str, p: Principal = read) -> list[ContextEntryOut]:
    """Context entries this session produced — the provenance link in reverse (§9)."""
    row, _reason, _ctx = load_visible_session(p, session_id)
    return [entry_out(p, e) for e in context_repo.list_by_session(p.org_id, row["id"])]


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: str, p: Principal = write) -> Response:
    row, _reason, _ctx = load_visible_session(p, session_id)
    if not can_edit_session(p, row):
        raise err("SESSION_READ_ONLY", "Only the session author or an admin can delete it.", status.HTTP_403_FORBIDDEN)
    sessions_repo.delete_session(p.org_id, session_id)
    record_audit(p, "session.delete", "ok", feature_id=row["feature_id"], session_id=session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
