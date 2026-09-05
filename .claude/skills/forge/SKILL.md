---
name: forge
description: Use Forge's shared engineering context before investigating a feature, and contribute durable knowledge back when you finish. Invoke whenever work touches a named product feature (LOGIN, PAYMENT, DOCUMENT_PROCESSING, USER_CREATION, NOTIFICATION, or anything the user calls a feature), before reading code to "understand how X works", and at checkpoints or session end.
when_to_use: Any engineering task on a feature this organization tracks in Forge; any time you would otherwise start from scratch to understand a feature; before context compaction; when finishing a piece of work.
allowed-tools: mcp__forge__forge_feature_get mcp__forge__forge_context_get mcp__forge__forge_context_search mcp__forge__forge_context_record mcp__forge__forge_context_supersede mcp__forge__forge_session_start mcp__forge__forge_session_checkpoint mcp__forge__forge_session_complete
---

# Forge: shared engineering context

Forge is the organization's Context Bank. A **session is history** (what happened); a **context entry is
knowledge** (what we currently know). Your job is to use the knowledge that exists and leave behind
knowledge that is durable, provenance-backed and true. Authorization, validation, versioning and audit are
enforced by the Forge server; this skill is behaviour, not the security boundary.

## 1. Identify the feature

Work in Forge is scoped to a **feature** (e.g. `PAYMENT`). Determine which feature the task belongs to from the
user's request, the code area, or by calling `forge_feature_get` with a likely key. If it is genuinely unclear,
ask the user once. Do not guess across features.

## 2. Retrieve before you investigate

**Before** independent investigation of the feature — reading code to understand it, tracing flows, forming a
design — call `forge_context_get(feature)`. If you have a specific question, `forge_context_search(query)` as
well. Read what comes back: decisions carry reasons, constraints are non-negotiable, known issues are traps,
open questions are things nobody has settled.

Do **not** call Forge before every file read or grep. Forge sits before investigation, not in front of every
filesystem operation.

## 3. Use what is relevant

If existing context answers the question, use it and say so ("Forge records that …"). Cite the entry when a
decision constrains what you do. Prefer current code, tests and runtime evidence over stale context — if they
disagree, that is a supersede case (step 6), not a reason to silently ignore Forge.

## 4. Discover locally when context is missing

If Forge has nothing relevant, or it is insufficient, investigate the code as you normally would. Track what you
learn that is **durable**: decisions and their reasons, constraints, architecture facts, known issues, open
questions, dependencies, and the files/tests that evidence them.

## 5. Contribute durable knowledge

Start a session first: `forge_session_start(feature, goal)`. Keep its `session_id`.

Record statements with `forge_context_record(feature, kind, title, payload, session_id, confidence, evidence,
request_id)`:

- `kind`: `decision` | `constraint` | `architecture` | `change` | `known_issue` | `open_question`
- `title`: short and quotable — one sentence someone can act on
- `payload`: for a decision `{decision, reason}`; for a constraint `{constraint}`; for a known issue
  `{issue, workaround?}`; for an open question `{question}`
- `confidence`: 0–1. Below 0.4 is held for human review rather than published
- `evidence`: `{files, tests, commit, symbols, observations}` when you have them
- `request_id`: a fresh UUID per statement; reuse it if you retry

**Never** record raw transcript, temporary observations, "I looked at file X", or half-formed guesses. If it
would not be worth reading in three months, it is not context.

## 6. Supersede, don't compete

If what you find contradicts an existing entry, call `forge_context_supersede(entry_id, title, payload,
session_id, evidence)` with the corrected statement. The old version is kept and marked superseded — nothing is
lost — and the feature no longer carries two conflicting truths. Do not record a second, contradictory entry.

## 7. Checkpoint and complete

Before context compaction, and at any natural pause, call `forge_session_checkpoint(session_id, contract)` with a
Context Contract summarising the work so far:

```
objective, changes[], decisions[{decision, reason}], affected_components[],
constraints[], dependencies[], known_issues[], open_questions[], confidence
```

When the work is done, `forge_session_complete(session_id, contract, summary)`. Both fan the contract out into
typed entries with this session as provenance. Both are idempotent — retry safely.

## Quick reference

| Situation | Call |
|---|---|
| Task mentions a feature | `forge_feature_get` → `forge_context_get` |
| Specific question | `forge_context_search` |
| Starting real work | `forge_session_start` |
| Learned something durable | `forge_context_record` |
| Existing entry is wrong | `forge_context_supersede` |
| About to compact / pausing | `forge_session_checkpoint` |
| Done | `forge_session_complete` |
