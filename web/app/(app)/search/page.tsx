import Link from "next/link";
import { Search } from "lucide-react";

import { ContextStatusBadge, KindBadge } from "@/components/badges";
import { nativeSelectClass } from "@/components/forms/field";
import { EmptyState, PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { get } from "@/lib/api";
import { formatRelative } from "@/lib/format";
import { CONTEXT_KINDS, type ContextEntry } from "@/lib/types";

/**
 * Context search. Metadata filtering plus plain-text matching over the stored
 * TOON — deliberately not semantic, since Phase 1 defers vector search until
 * simple retrieval proves insufficient.
 */
export default async function SearchPage({ searchParams }: PageProps<"/search">) {
  const sp = await searchParams;
  const q = typeof sp.q === "string" ? sp.q.trim() : "";
  const kind = typeof sp.kind === "string" ? sp.kind : "";

  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (kind) params.set("kind", kind);

  const results = q.length >= 2 ? await get<ContextEntry[]>(`/context/search?${params}`) : [];

  return (
    <>
      <PageHeader
        eyebrow="Context Bank"
        title="Search context"
        description="Searches titles and payloads across every feature you can access. Features you cannot access never appear."
      />

      <form className="mb-6 flex flex-wrap items-end gap-3">
        <div className="grid min-w-64 flex-1 gap-1.5">
          <label htmlFor="q" className="text-sm font-medium">
            Query
          </label>
          <Input id="q" name="q" defaultValue={q} placeholder="idempotency, rotation, ledger…" minLength={2} />
        </div>
        <div className="grid gap-1.5">
          <label htmlFor="kind" className="text-sm font-medium">
            Kind
          </label>
          <select
            id="kind"
            name="kind"
            defaultValue={kind}
            className={nativeSelectClass}
          >
            <option value="">Any kind</option>
            {CONTEXT_KINDS.map((k) => (
              <option key={k} value={k}>
                {k.replace("_", " ")}
              </option>
            ))}
          </select>
        </div>
        <Button type="submit">
          <Search data-icon="inline-start" />
          Search
        </Button>
      </form>

      {q.length < 2 ? (
        <EmptyState title="Type at least two characters" body="Results are scoped to your authorized features." />
      ) : results.length === 0 ? (
        <EmptyState title={`Nothing matches “${q}”`} body="Try a broader term, or clear the kind filter." />
      ) : (
        <>
          <p className="text-muted-foreground mb-3 text-sm">
            {results.length} {results.length === 1 ? "match" : "matches"}
          </p>
          <ol className="divide-border/60 divide-y">
            {results.map((e) => (
              <li key={e.id} className="py-4">
                <div className="flex flex-wrap items-center gap-2">
                  <KindBadge kind={e.kind} />
                  <Link href={`/context/${e.id}`} className="font-medium hover:underline">
                    {e.title}
                  </Link>
                  <ContextStatusBadge status={e.status} />
                  {e.feature && (
                    <Link href={`/features/${e.feature.id}`}>
                      <Badge variant="secondary" className="font-mono hover:bg-muted">
                        {e.feature.key}
                      </Badge>
                    </Link>
                  )}
                  <span className="text-muted-foreground ml-auto font-mono text-xs">v{e.version}</span>
                </div>
                <p className="text-muted-foreground mt-1 text-xs">
                  {e.author?.display_name ?? e.author_user_id ?? "unknown"} · {formatRelative(e.created_at)}
                </p>
              </li>
            ))}
          </ol>
        </>
      )}
    </>
  );
}
