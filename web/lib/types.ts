// Mirrors api/app/schemas.py

export type Role = "admin" | "developer" | "qa";
export type SessionStatus = "active" | "completed" | "failed" | "abandoned";
export type FeatureStatus = "active" | "archived";
export type ContextKind = "decision" | "constraint" | "architecture" | "change" | "known_issue" | "open_question";
export type ContextStatus = "active" | "superseded" | "pending_review" | "rejected";

export const CONTEXT_KINDS: ContextKind[] = [
  "decision",
  "constraint",
  "architecture",
  "change",
  "known_issue",
  "open_question",
];

export interface User {
  id: string;
  clerk_org_id: string;
  email: string | null;
  display_name: string;
  avatar_url: string | null;
  role: Role | string;
  is_demo: boolean;
}

export interface TeamSummary {
  id: string;
  name: string;
}

export interface Team extends TeamSummary {
  clerk_org_id: string;
  description: string | null;
  created_at: string;
  members: User[];
}

export interface Me {
  principal: { user_id: string; org_id: string; role: Role; clerk_role: string };
  user: User;
  organization: { clerk_org_id: string; name: string; slug: string | null };
  teams: TeamSummary[];
}

export interface FeatureSummary {
  id: string;
  key: string;
  name: string;
}

export interface Feature extends FeatureSummary {
  clerk_org_id: string;
  description: string | null;
  status: FeatureStatus;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  access_reason: "admin" | "assigned" | "team" | null;
  teams: TeamSummary[];
  assignees: User[];
  session_count: number;
}

export interface Decision {
  decision: string;
  reason: string | null;
}

/** The Context Contract (phase-1-requirements §6). */
export interface ContextContract {
  objective: string;
  changes: string[];
  decisions: Decision[];
  affected_components: string[];
  constraints: string[];
  dependencies: string[];
  known_issues: string[];
  open_questions: string[];
  confidence: number;
}

export interface Session {
  id: string;
  clerk_org_id: string;
  feature_id: string;
  user_id: string;
  agent: string;
  model: string | null;
  status: SessionStatus;
  goal: string | null;
  summary: string | null;
  /** Non-authoritative snapshot of the generated contract; the Context Bank is the source of truth. */
  context: ContextContract | null;
  context_version: number;
  started_at: string;
  ended_at: string | null;
  created_at: string;
  updated_at: string;
  author: User | null;
  feature: FeatureSummary | null;
  visibility_reason: string | null; // admin | own | team:<name>
}

export interface ContextEntry {
  id: string;
  feature_id: string;
  session_id: string | null;
  author_user_id: string | null;
  kind: ContextKind;
  version: number;
  title: string;
  payload: Record<string, unknown>;
  confidence: number | null;
  status: ContextStatus;
  supersedes_id: string | null;
  /** Set when this statement was flagged as resembling an active one (§17). */
  conflicts_with: string | null;
  evidence: Record<string, unknown> | null;
  created_at: string;
  updated_at: string | null;
  // Provenance: context → source session → author.
  author: User | null;
  session: Session | null;
  feature: FeatureSummary | null;
}

export interface ValidationIssue {
  field: string;
  code: string;
  message: string;
}

export interface CompletionResult {
  session: Session;
  context_entries: ContextEntry[];
  generated: boolean;
  contract: ContextContract | null;
  validation_issues: ValidationIssue[];
  quarantined: boolean;
  idempotent_replay: boolean;
}

export interface FeatureDetail extends Feature {
  sessions: Session[];
  hidden_session_count: number;
  context_entries: ContextEntry[];
}

// --- Phase 2: agent credentials (OAuth grants) ---------------------------------

export type AgentScope = "context.read" | "context.write" | "context.supersede" | "session.write";

export const AGENT_SCOPE_LABELS: Record<AgentScope, string> = {
  "context.read": "Read feature context and search the Context Bank",
  "context.write": "Record new context statements",
  "context.supersede": "Replace existing statements with newer versions",
  "session.write": "Start, checkpoint and complete sessions",
};

/** What an OAuth client is asking for, shown on the consent page. */
export interface PendingAuthorization {
  id: string;
  client_id: string;
  client_name: string;
  scopes: string[];
  redirect_uri: string | null;
  expires_at: string;
}

/** An agent credential: the consented OAuth grant (phase-2 §5.1). */
export interface AgentGrant {
  id: string;
  clerk_org_id: string;
  user_id: string;
  client_id: string;
  client_name: string | null;
  scopes: string[];
  feature_ids: string[] | null;
  status: "active" | "revoked";
  created_at: string;
  expires_at: string | null;
  revoked_at: string | null;
  last_used_at: string | null;
  creator: User | null;
  features: FeatureSummary[];
}

export interface SeedResult {
  created: Record<string, number>;
  message: string;
}

export interface SyncResult {
  synced: number;
  message: string;
}
