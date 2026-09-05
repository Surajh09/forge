"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { ApiError, del, patch, post } from "@/lib/api";
import type {
  CompletionResult,
  ContextContract,
  ContextEntry,
  ContextKind,
  ContextStatus,
  Decision,
  FeatureDetail,
  SeedResult,
  Session,
  SyncResult,
  Team,
} from "@/lib/types";

export type ActionState = { ok: boolean; message: string } | null;

function failure(e: unknown): ActionState {
  const message = e instanceof ApiError || e instanceof Error ? e.message : "Unexpected error";
  return { ok: false, message };
}

const str = (fd: FormData, key: string) => String(fd.get(key) ?? "").trim();
const optional = (fd: FormData, key: string) => str(fd, key) || null;
const lines = (fd: FormData, key: string) =>
  str(fd, key)
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);

// --- features ---------------------------------------------------------------

export async function createFeatureAction(_prev: ActionState, fd: FormData): Promise<ActionState> {
  let created: FeatureDetail;
  try {
    created = await post<FeatureDetail>("/features", {
      key: str(fd, "key").toUpperCase().replace(/[\s-]+/g, "_"),
      name: str(fd, "name"),
      description: optional(fd, "description"),
      team_ids: fd.getAll("team_ids").map(String),
      assignee_ids: fd.getAll("assignee_ids").map(String),
    });
  } catch (e) {
    return failure(e);
  }
  revalidatePath("/features");
  revalidatePath("/dashboard");
  redirect(`/features/${created.id}`);
}

export async function updateFeatureAction(featureId: string, _prev: ActionState, fd: FormData): Promise<ActionState> {
  try {
    await patch(`/features/${featureId}`, {
      name: str(fd, "name"),
      description: optional(fd, "description"),
      status: str(fd, "status") || undefined,
    });
  } catch (e) {
    return failure(e);
  }
  revalidatePath(`/features/${featureId}`);
  revalidatePath("/features");
  return { ok: true, message: "Feature updated." };
}

export async function deleteFeatureAction(featureId: string): Promise<void> {
  await del(`/features/${featureId}`);
  revalidatePath("/features");
  revalidatePath("/dashboard");
  redirect("/features");
}

export async function setFeatureLinkAction(
  kind: "teams" | "assignees",
  featureId: string,
  targetId: string,
  add: boolean,
): Promise<void> {
  if (!targetId) return;
  if (add) await post(`/features/${featureId}/${kind}/${targetId}`);
  else await del(`/features/${featureId}/${kind}/${targetId}`);
  revalidatePath(`/features/${featureId}`);
  revalidatePath("/features");
}

export async function featureLinkFormAction(kind: "teams" | "assignees", featureId: string, add: boolean, fd: FormData) {
  await setFeatureLinkAction(kind, featureId, str(fd, "target_id"), add);
}

// --- teams ------------------------------------------------------------------

export async function createTeamAction(_prev: ActionState, fd: FormData): Promise<ActionState> {
  try {
    await post<Team>("/teams", { name: str(fd, "name"), description: optional(fd, "description") });
  } catch (e) {
    return failure(e);
  }
  revalidatePath("/admin");
  return { ok: true, message: "Team created." };
}

export async function deleteTeamAction(teamId: string): Promise<void> {
  await del(`/teams/${teamId}`);
  revalidatePath("/admin");
  revalidatePath("/features");
}

export async function addTeamMemberAction(teamId: string, fd: FormData): Promise<void> {
  const userId = str(fd, "user_id");
  if (!userId) return;
  await post(`/teams/${teamId}/members/${userId}`);
  revalidatePath("/admin");
  revalidatePath("/features");
}

export async function removeTeamMemberAction(teamId: string, userId: string): Promise<void> {
  await del(`/teams/${teamId}/members/${userId}`);
  revalidatePath("/admin");
  revalidatePath("/features");
}

// --- sessions ---------------------------------------------------------------

export async function startSessionAction(featureId: string, _prev: ActionState, fd: FormData): Promise<ActionState> {
  let created: Session;
  try {
    created = await post<Session>("/sessions", {
      feature_id: featureId,
      agent: str(fd, "agent") || "manual",
      model: optional(fd, "model"),
      goal: optional(fd, "goal"),
    });
  } catch (e) {
    return failure(e);
  }
  revalidatePath(`/features/${featureId}`);
  revalidatePath("/sessions");
  revalidatePath("/dashboard");
  redirect(`/sessions/${created.id}`);
}

export async function updateSessionAction(sessionId: string, _prev: ActionState, fd: FormData): Promise<ActionState> {
  try {
    await patch(`/sessions/${sessionId}`, {
      goal: optional(fd, "goal"),
      summary: optional(fd, "summary"),
      status: str(fd, "status") || undefined,
    });
  } catch (e) {
    return failure(e);
  }
  revalidatePath(`/sessions/${sessionId}`);
  revalidatePath("/sessions");
  return { ok: true, message: "Session updated." };
}

export async function completeSessionAction(sessionId: string, _prev: ActionState, fd: FormData): Promise<ActionState> {
  // "decisions" is one per line as `decision — reason` (the em dash is optional).
  const decisions: Decision[] = lines(fd, "decisions").map((line) => {
    const [decision, ...rest] = line.split(/\s+[—-]{1,2}\s+/);
    return { decision: decision.trim(), reason: rest.join(" - ").trim() || null };
  });

  // Omitting the contract entirely hands the job to the Context Generator.
  const useGenerator = str(fd, "mode") === "generate";
  const contract: ContextContract | undefined = useGenerator
    ? undefined
    : {
        objective: str(fd, "objective"),
        changes: lines(fd, "changes"),
        decisions,
        affected_components: lines(fd, "affected_components"),
        dependencies: lines(fd, "dependencies"),
        constraints: lines(fd, "constraints"),
        known_issues: lines(fd, "known_issues"),
        open_questions: lines(fd, "open_questions"),
        confidence: Number(str(fd, "confidence") || "0"),
      };

  let result: CompletionResult;
  try {
    result = await post<CompletionResult>(`/sessions/${sessionId}/complete`, {
      context: contract,
      summary: optional(fd, "summary"),
      status: str(fd, "status") || "completed",
    });
  } catch (e) {
    return failure(e);
  }

  revalidatePath(`/sessions/${sessionId}`);
  revalidatePath(`/features/${result.session.feature_id}`);
  revalidatePath("/sessions");
  revalidatePath("/dashboard");

  const n = result.context_entries.length;
  if (result.idempotent_replay) {
    return { ok: true, message: `Already completed. ${n} existing context ${n === 1 ? "entry" : "entries"} left untouched.` };
  }
  const written = `${n} context ${n === 1 ? "entry" : "entries"} written to the Context Bank`;
  if (result.quarantined) {
    return {
      ok: true,
      message: `Session ${result.session.status}. ${written}, held as pending review because confidence was too low to publish.`,
    };
  }
  return {
    ok: true,
    message: `Session ${result.session.status}. ${written}${result.generated ? " from generated context" : ""}.`,
  };
}

export async function deleteSessionAction(sessionId: string, featureId: string): Promise<void> {
  await del(`/sessions/${sessionId}`);
  revalidatePath(`/features/${featureId}`);
  revalidatePath("/sessions");
  redirect(`/features/${featureId}`);
}

// --- context bank -----------------------------------------------------------

/** Author a context statement by hand (record_context). */
export async function recordContextAction(featureId: string, _prev: ActionState, fd: FormData): Promise<ActionState> {
  const body = str(fd, "body");
  const kind = str(fd, "kind") as ContextKind;

  // Each kind names its payload field so entries read naturally downstream.
  const payloadKey =
    kind === "decision" ? "decision" : kind === "constraint" ? "constraint" : kind === "known_issue" ? "issue" : kind === "open_question" ? "question" : "note";
  const payload: Record<string, unknown> = { [payloadKey]: body || str(fd, "title") };
  const reason = optional(fd, "reason");
  if (reason) payload.reason = reason;

  try {
    await post<ContextEntry>(`/features/${featureId}/context`, {
      kind,
      title: str(fd, "title"),
      payload,
      confidence: fd.get("confidence") ? Number(str(fd, "confidence")) : null,
      session_id: optional(fd, "session_id"),
    });
  } catch (e) {
    return failure(e);
  }
  revalidatePath(`/features/${featureId}`);
  return { ok: true, message: "Context recorded." };
}

/** Revise a statement: writes a new version and supersedes the current one. */
export async function supersedeContextAction(entryId: string, _prev: ActionState, fd: FormData): Promise<ActionState> {
  const existingKeys = str(fd, "payload_keys").split(",").filter(Boolean);
  const payload: Record<string, unknown> = {};
  for (const key of existingKeys) {
    const value = str(fd, `payload__${key}`);
    if (value) payload[key] = value;
  }

  let updated: ContextEntry;
  try {
    updated = await patch<ContextEntry>(`/context/${entryId}`, {
      title: str(fd, "title"),
      payload,
      confidence: fd.get("confidence") ? Number(str(fd, "confidence")) : undefined,
    });
  } catch (e) {
    return failure(e);
  }
  revalidatePath(`/context/${entryId}`);
  revalidatePath(`/context/${updated.id}`);
  revalidatePath(`/features/${updated.feature_id}`);
  redirect(`/context/${updated.id}`);
}

/** Approve or reject quarantined context. */
export async function setContextStatusAction(entryId: string, status: ContextStatus, featureId: string): Promise<void> {
  await patch<ContextEntry>(`/context/${entryId}`, { status });
  revalidatePath("/review");
  revalidatePath(`/context/${entryId}`);
  revalidatePath(`/features/${featureId}`);
}

// --- admin ------------------------------------------------------------------

export async function seedDemoAction(): Promise<ActionState> {
  let result: SeedResult;
  try {
    result = await post<SeedResult>("/admin/seed");
  } catch (e) {
    return failure(e);
  }
  revalidatePath("/", "layout");
  const parts = Object.entries(result.created)
    .filter(([, n]) => n > 0)
    .map(([k, n]) => `${n} ${k.replace("_", " ")}`);
  return { ok: true, message: parts.length ? `Created ${parts.join(", ")}.` : "Demo data was already present — nothing new created." };
}

export async function syncMembersAction(): Promise<ActionState> {
  let result: SyncResult;
  try {
    result = await post<SyncResult>("/admin/sync-members");
  } catch (e) {
    return failure(e);
  }
  revalidatePath("/", "layout");
  return { ok: true, message: result.message };
}

// --- agent credentials -------------------------------------------------------

/** Revoke a grant: every token bound to it stops working immediately. */
export async function revokeGrantAction(grantId: string): Promise<void> {
  await del(`/oauth/grants/${grantId}`);
  revalidatePath("/agent");
}

// --- MCP OAuth consent -----------------------------------------------------

type ConsentRedirect = { redirect_url: string };

/** Approve a pending MCP OAuth request, then return the client to its callback. */
export async function approveAgentConsentAction(txn: string, fd: FormData): Promise<never> {
  const restricted = fd.get("restrict_features") === "on";
  const featureIds = restricted ? fd.getAll("feature_ids").map(String).filter(Boolean) : null;
  // Ticked scopes only; the server refuses anything the client did not request.
  const scopes = fd.getAll("scopes").map(String).filter(Boolean);
  const result = await post<ConsentRedirect>(`/oauth/consents/${txn}/approve`, {
    feature_ids: featureIds,
    scopes,
  });
  redirect(result.redirect_url);
}

/** Deny a pending MCP OAuth request, preserving the client's OAuth state. */
export async function denyAgentConsentAction(txn: string): Promise<never> {
  const result = await post<ConsentRedirect>(`/oauth/consents/${txn}/deny`);
  redirect(result.redirect_url);
}
