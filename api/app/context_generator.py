"""Context Generator (phase-1-requirements §7).

Turns a session plus whatever information is available about it into a Context
Contract. It **must not write to the Context Bank** — it returns a contract and
nothing else. Persistence is the caller's job, and only after validation:

    Session → Generator → Contract → Validator → Context Bank

Phase 1 ships a deterministic generator. There is no transcript to read yet, so
it derives what it can from session metadata and is honest about the result by
returning a low confidence. The `ContextGenerator` protocol is the seam: an
LLM-backed generator can replace it later without the Context Bank API changing.
"""

from __future__ import annotations

import re
from typing import Any, Protocol

from app.schemas import ContextContract, Decision

# Confidence assigned to context nobody reviewed, derived only from metadata.
DERIVED_CONFIDENCE = 0.3

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


class ContextGenerator(Protocol):
    """Anything that can turn a session into a Context Contract."""

    name: str

    def generate(self, session: dict[str, Any]) -> ContextContract: ...


def _sentences(text: str | None) -> list[str]:
    if not text:
        return []
    return [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]


class DeterministicGenerator:
    """Metadata-only generator: same session in, same contract out.

    Deliberately conservative. It records what the session says about itself and
    flags the gap as an open question rather than inventing engineering detail.
    """

    name = "deterministic-v1"

    def generate(self, session: dict[str, Any]) -> ContextContract:
        goal = (session.get("goal") or "").strip()
        summary = (session.get("summary") or "").strip()
        agent = session.get("agent") or "unknown agent"
        model = session.get("model")

        objective = goal or summary or f"Untitled {agent} session"

        changes = _sentences(summary)
        if not changes and goal:
            changes = [f"Worked on: {goal}"]

        actor = f"{agent} ({model})" if model else agent
        open_questions = [
            f"Context for this session was derived from metadata by {self.name}, not from a transcript. "
            f"Confirm with the author before relying on it."
        ]

        return ContextContract(
            objective=objective[:2000],
            changes=changes,
            decisions=[],
            affected_components=[],
            constraints=[],
            dependencies=[],
            known_issues=[],
            open_questions=open_questions,
            confidence=DERIVED_CONFIDENCE,
        )


class NullGenerator:
    """Used when a caller supplies its own contract; records provenance only."""

    name = "author-supplied"

    def generate(self, session: dict[str, Any]) -> ContextContract:  # pragma: no cover
        raise NotImplementedError("NullGenerator never generates; a contract must be supplied.")


_default = DeterministicGenerator()


def get_generator() -> ContextGenerator:
    """Swap point for a future LLM-backed generator."""
    return _default


__all__ = [
    "ContextGenerator",
    "DeterministicGenerator",
    "NullGenerator",
    "Decision",
    "get_generator",
    "DERIVED_CONFIDENCE",
]
