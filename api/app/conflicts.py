"""Conflict detection for the Context Bank (phase-2 §17).

Forge must never silently overwrite durable knowledge, and must detect or flag
contradictions. Automatic resolution is explicitly out of scope, so this module
only *notices*: it compares a candidate statement against the active entries of
the same feature and kind, and reports the closest match above a threshold.

The caller quarantines the newcomer as `pending_review` with `conflicts_with`
set, which routes it to the existing review queue for a human to supersede or
keep. Both sides stay readable either way.

Pure functions over plain data, so the similarity rule is unit-testable without
a database and can be tuned in one place.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Iterable, Mapping

# Above this, two statements are treated as the same claim restated.
SIMILARITY_THRESHOLD = 0.72

# Words too common in engineering prose to carry meaning when comparing.
_STOP = frozenset(
    """a an and are as at be but by for from has have if in into is it its of on or that the
    their then there these this to was were will with when where which while must should not""".split()
)
_WORD = re.compile(r"[a-z0-9_./-]+")


def _stem(word: str) -> str:
    """Crude plural/verb folding so 'retries'/'retry' and 'keys'/'key' match.

    Deliberately not a real stemmer: engineering statements get reworded
    between singular and plural far more often than they get conjugated, and a
    heavier stemmer would create false matches between unrelated claims.
    """
    # Minimum lengths differ per suffix: "keys" is only four characters, so a
    # single guard either misses it or mangles short words like "ies".
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith("es"):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _tokens(text: str) -> set[str]:
    return {_stem(w) for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 2}


def _statement_text(title: str, payload: Mapping[str, Any]) -> str:
    """Title plus the payload's own prose, ignoring structural keys."""
    parts = [title]
    for key, value in payload.items():
        if key in {"reason", "rationale", "impact", "workaround", "fix_sketch", "note", "notes"}:
            continue  # supporting detail, not the claim itself
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, (list, tuple)):
            parts.extend(str(v) for v in value if isinstance(v, (str, int, float)))
    return " ".join(parts)


def similarity(a: str, b: str) -> float:
    """Blend token overlap with sequence similarity.

    Token overlap catches the same claim reworded; sequence similarity catches
    near-verbatim restatements that share few distinctive words. Taking the
    larger of the two makes the check hard to slip past by paraphrasing.
    """
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    jaccard = len(ta & tb) / len(ta | tb)
    ratio = SequenceMatcher(None, a.lower(), b.lower()).ratio()
    return max(jaccard, ratio)


@dataclass(frozen=True)
class ConflictMatch:
    entry_id: str
    title: str
    score: float


def find_conflict(
    *,
    kind: str,
    title: str,
    payload: Mapping[str, Any],
    existing: Iterable[Mapping[str, Any]],
    threshold: float = SIMILARITY_THRESHOLD,
) -> ConflictMatch | None:
    """Closest active entry of the same kind that this statement resembles.

    Only same-kind entries are compared: a decision and the constraint it
    implies often share wording without being in conflict.
    """
    candidate = _statement_text(title, payload)
    best: ConflictMatch | None = None
    for row in existing:
        if row.get("kind") != kind or row.get("status") != "active":
            continue
        score = similarity(candidate, _statement_text(row.get("title", ""), row.get("payload") or {}))
        if score >= threshold and (best is None or score > best.score):
            best = ConflictMatch(entry_id=str(row["id"]), title=row.get("title", ""), score=round(score, 3))
    return best
