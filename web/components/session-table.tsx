import Link from "next/link";

import { AgentBadge, StatusBadge, VisibilityBadge } from "@/components/badges";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDuration, formatRelative } from "@/lib/format";
import type { Session } from "@/lib/types";

export function SessionTable({ sessions, showFeature = false }: { sessions: Session[]; showFeature?: boolean }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Goal</TableHead>
          {showFeature && <TableHead>Feature</TableHead>}
          <TableHead>Author</TableHead>
          <TableHead>Agent</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Started</TableHead>
          <TableHead>Duration</TableHead>
          <TableHead>Visible because</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sessions.map((s) => (
          <TableRow key={s.id}>
            {/* TableCell is whitespace-nowrap, so a max-width alone cannot contain
                the goal — it needs an explicit truncate. min-w-0 lets the link
                shrink below its text width inside the flex row. */}
            <TableCell className="max-w-[36ch]">
              <div className="flex items-center gap-2">
                <Link
                  href={`/sessions/${s.id}`}
                  title={s.goal ?? "Untitled session"}
                  className="min-w-0 truncate font-medium hover:underline"
                >
                  {s.goal ?? "Untitled session"}
                </Link>
                {s.context_version > 0 && (
                  <span className="text-muted-foreground shrink-0 font-mono text-xs">ctx v{s.context_version}</span>
                )}
              </div>
            </TableCell>
            {showFeature && (
              <TableCell>
                {s.feature ? (
                  <Link href={`/features/${s.feature.id}`} className="font-mono text-xs hover:underline">
                    {s.feature.key}
                  </Link>
                ) : (
                  "—"
                )}
              </TableCell>
            )}
            <TableCell>{s.author?.display_name ?? s.user_id}</TableCell>
            <TableCell>
              <AgentBadge agent={s.agent} model={s.model} />
            </TableCell>
            <TableCell>
              <StatusBadge status={s.status} />
            </TableCell>
            <TableCell className="text-muted-foreground">{formatRelative(s.started_at)}</TableCell>
            <TableCell className="text-muted-foreground">{formatDuration(s.started_at, s.ended_at)}</TableCell>
            <TableCell>
              <VisibilityBadge reason={s.visibility_reason} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
