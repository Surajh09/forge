"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { CONTEXT_KINDS, type ContextKind } from "@/lib/types";
import { cn } from "@/lib/utils";

const STATUSES = [
  { value: "", label: "Active" },
  { value: "pending_review", label: "Pending review" },
  { value: "superseded", label: "Superseded" },
  { value: "rejected", label: "Rejected" },
];

/** Kind and status filters for a feature's Context tab, driven by the URL. */
export function ContextFilters({ counts }: { counts: Partial<Record<ContextKind, number>> }) {
  const pathname = usePathname();
  const params = useSearchParams();
  const activeKind = params.get("kind") ?? "";
  const activeStatus = params.get("status") ?? "";

  const href = (next: { kind?: string; status?: string }) => {
    const p = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(next)) {
      if (v) p.set(k, v);
      else p.delete(k);
    }
    p.set("tab", "context");
    const qs = p.toString();
    return `${pathname}${qs ? `?${qs}` : ""}`;
  };

  return (
    <div className="mb-4 grid gap-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-muted-foreground mr-1 text-xs font-medium uppercase">Kind</span>
        <Link href={href({ kind: "" })}>
          <Badge variant={activeKind ? "outline" : "default"} className="hover:bg-muted">
            All
          </Badge>
        </Link>
        {CONTEXT_KINDS.filter((k) => counts[k]).map((k) => (
          <Link key={k} href={href({ kind: k })}>
            <Badge variant={activeKind === k ? "default" : "outline"} className="hover:bg-muted">
              {k.replace("_", " ")}
              <span className={cn("ml-1 tabular-nums", activeKind === k ? "opacity-80" : "text-muted-foreground")}>
                {counts[k]}
              </span>
            </Badge>
          </Link>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-muted-foreground mr-1 text-xs font-medium uppercase">Status</span>
        {STATUSES.map((s) => (
          <Link key={s.value} href={href({ status: s.value })}>
            <Badge variant={activeStatus === s.value ? "default" : "outline"} className="hover:bg-muted">
              {s.label}
            </Badge>
          </Link>
        ))}
      </div>
    </div>
  );
}
