import Link from "next/link";
import { ArrowUpRight } from "lucide-react";

import { ContextStatusBadge, KindBadge } from "@/components/badges";
import { formatRelative } from "@/lib/format";
import type { ContextContract, ContextEntry } from "@/lib/types";

const LIST_FIELDS: { key: keyof ContextContract; label: string }[] = [
  { key: "changes", label: "Changes" },
  { key: "affected_components", label: "Affected components" },
  { key: "dependencies", label: "Dependencies" },
  { key: "constraints", label: "Constraints" },
  { key: "known_issues", label: "Known issues" },
  { key: "open_questions", label: "Open questions" },
];

/** The full Context Contract, as recorded on a session. */
export function ContextView({ context }: { context: ContextContract }) {
  const filled = LIST_FIELDS.filter(({ key }) => (context[key] as string[])?.length > 0);
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div className="sm:col-span-2">
        <div className="text-muted-foreground text-xs font-medium uppercase">Objective</div>
        <p className="mt-1 text-sm">{context.objective}</p>
      </div>

      {context.decisions?.length > 0 && (
        <div className="sm:col-span-2">
          <div className="text-muted-foreground text-xs font-medium uppercase">Technical decisions</div>
          <ul className="mt-1 space-y-1.5 text-sm">
            {context.decisions.map((d, i) => (
              <li key={i}>
                <span className="font-medium">{d.decision}</span>
                {d.reason && <span className="text-muted-foreground"> — {d.reason}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {filled.map(({ key, label }) => (
        <div key={key}>
          <div className="text-muted-foreground text-xs font-medium uppercase">{label}</div>
          <ul className="mt-1 list-disc space-y-0.5 pl-4 text-sm">
            {(context[key] as string[]).map((item, i) => (
              <li key={i} className={key === "affected_components" ? "font-mono text-xs" : undefined}>
                {item}
              </li>
            ))}
          </ul>
        </div>
      ))}

      <div className="sm:col-span-2">
        <div className="text-muted-foreground text-xs font-medium uppercase">Confidence</div>
        <ConfidenceBar value={context.confidence} />
      </div>
    </div>
  );
}

export function ConfidenceBar({ value }: { value: number | null }) {
  if (value == null) return <span className="text-muted-foreground text-xs">n/a</span>;
  const pct = Math.round(value * 100);
  return (
    <div className="mt-1 flex items-center gap-2">
      <div className="bg-muted h-1.5 w-32 overflow-hidden rounded-full">
        <div className="bg-primary h-full rounded-full" style={{ width: `${pct}%` }} />
      </div>
      <span className="font-mono text-xs">{pct}%</span>
    </div>
  );
}

/** Renders one entry's payload without assuming a fixed shape. */
function PayloadView({ payload }: { payload: Record<string, unknown> }) {
  const entries = Object.entries(payload).filter(([, v]) => {
    if (v == null || v === "") return false;
    if (Array.isArray(v)) return v.length > 0;
    return true;
  });
  if (entries.length === 0) return null;

  return (
    <dl className="mt-2 grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[10rem_1fr]">
      {entries.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-muted-foreground capitalize">{k.replace(/_/g, " ")}</dt>
          <dd>{Array.isArray(v) ? v.map(String).join(", ") : String(v)}</dd>
        </div>
      ))}
    </dl>
  );
}

export function ContextEntryList({ entries }: { entries: ContextEntry[] }) {
  return (
    <ol className="divide-border/60 divide-y">
      {entries.map((e) => (
        <li key={e.id} className="py-4">
          <div className="flex flex-wrap items-center gap-2">
            <KindBadge kind={e.kind} />
            <Link href={`/context/${e.id}`} className="font-medium hover:underline">
              {e.title}
            </Link>
            <ContextStatusBadge status={e.status} />
            <span className="text-muted-foreground ml-auto font-mono text-xs">v{e.version}</span>
          </div>

          <PayloadView payload={e.payload} />

          <div className="text-muted-foreground mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
            <span>{e.author?.display_name ?? e.author_user_id ?? "unknown author"}</span>
            <span>·</span>
            <span>{formatRelative(e.created_at)}</span>
            {e.confidence != null && (
              <>
                <span>·</span>
                <span>confidence {Math.round(e.confidence * 100)}%</span>
              </>
            )}
            {e.session_id && (
              <>
                <span>·</span>
                <Link
                  href={`/sessions/${e.session_id}`}
                  className="inline-flex items-center gap-0.5 hover:underline"
                >
                  from {e.session?.goal ?? `session ${e.session_id.slice(0, 8)}`}
                  <ArrowUpRight className="size-3" />
                </Link>
              </>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}
