import { Badge } from "@/components/ui/badge";
import type { ContextKind, ContextStatus, SessionStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * Every badge derives its colour from one token per meaning (see globals.css),
 * rather than hardcoding a palette class per light/dark pair. The token flips
 * with the colour scheme, so each style below is a single string.
 */

const KIND_TOKEN: Record<ContextKind, string> = {
  decision: "bg-kind-decision/12 text-kind-decision border-kind-decision/35",
  constraint: "bg-kind-constraint/12 text-kind-constraint border-kind-constraint/35",
  architecture: "bg-kind-architecture/12 text-kind-architecture border-kind-architecture/35",
  change: "bg-kind-change/12 text-kind-change border-kind-change/35",
  known_issue: "bg-kind-known-issue/12 text-kind-known-issue border-kind-known-issue/35",
  open_question: "bg-kind-open-question/12 text-kind-open-question border-kind-open-question/35",
};

const SESSION_STATE: Record<SessionStatus, string> = {
  active: "bg-state-active/12 text-state-active border-state-active/35",
  completed: "bg-kind-change/12 text-kind-change border-kind-change/35",
  failed: "bg-state-rejected/12 text-state-rejected border-state-rejected/35",
  abandoned: "bg-state-neutral/12 text-state-neutral border-state-neutral/30",
};

const CONTEXT_STATE: Record<ContextStatus, string> = {
  active: "bg-state-active/12 text-state-active border-state-active/35",
  superseded: "bg-state-neutral/12 text-state-neutral border-state-neutral/30",
  pending_review: "bg-state-pending/12 text-state-pending border-state-pending/35",
  rejected: "bg-state-rejected/12 text-state-rejected border-state-rejected/35",
};

export function StatusBadge({ status }: { status: SessionStatus }) {
  return (
    <Badge variant="outline" className={cn("capitalize", SESSION_STATE[status])}>
      {status === "active" && (
        <span className="bg-state-active mr-1 inline-block size-1.5 animate-pulse rounded-full" />
      )}
      {status}
    </Badge>
  );
}

/** Why the viewer can see a session: own | team:<name> | admin */
export function VisibilityBadge({ reason }: { reason: string | null }) {
  if (!reason) return null;
  if (reason === "own") return <Badge variant="secondary">your session</Badge>;
  if (reason === "admin")
    return (
      <Badge variant="outline" className="bg-state-pending/12 text-state-pending border-state-pending/35">
        admin view
      </Badge>
    );
  if (reason.startsWith("team:"))
    return (
      <Badge variant="outline" className="bg-primary/10 text-primary border-primary/30">
        via {reason.slice(5)} team
      </Badge>
    );
  return <Badge variant="outline">{reason}</Badge>;
}

/** Why the viewer can access a feature: admin | assigned | team */
export function AccessBadge({ reason }: { reason: string | null }) {
  const label =
    reason === "admin"
      ? "admin"
      : reason === "assigned"
        ? "assigned to you"
        : reason === "team"
          ? "via your team"
          : reason;
  if (!label) return null;
  return (
    <Badge variant="outline" className="bg-primary/10 text-primary border-primary/30">
      {label}
    </Badge>
  );
}

export function KindBadge({ kind }: { kind: ContextKind }) {
  return (
    <Badge variant="outline" className={cn("font-medium", KIND_TOKEN[kind])}>
      {kind.replace("_", " ")}
    </Badge>
  );
}

/** Active is the normal case and stays unlabelled to keep lists quiet. */
export function ContextStatusBadge({ status }: { status: ContextStatus }) {
  if (status === "active") return null;
  return (
    <Badge variant="outline" className={cn(CONTEXT_STATE[status])}>
      {status.replace("_", " ")}
    </Badge>
  );
}

export function RoleBadge({ role }: { role: string }) {
  return (
    <Badge variant={role === "admin" ? "default" : "secondary"} className="capitalize">
      {role}
    </Badge>
  );
}

export function AgentBadge({ agent, model }: { agent: string; model: string | null }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs">
      <Badge variant="outline" className="font-mono">
        {agent}
      </Badge>
      {model && <span className="text-muted-foreground font-mono">{model}</span>}
    </span>
  );
}
