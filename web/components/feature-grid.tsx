"use client";

import Link from "next/link";
import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Archive, Users } from "lucide-react";

import { AccessBadge } from "@/components/badges";
import { Badge } from "@/components/ui/badge";
import type { Feature } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Aceternity "card hover effect" adapted to render Forge feature cards. */
export function FeatureGrid({ features, className }: { features: Feature[]; className?: string }) {
  const [hovered, setHovered] = useState<number | null>(null);

  return (
    <div className={cn("grid grid-cols-1 gap-1 md:grid-cols-2 lg:grid-cols-3", className)}>
      {features.map((f, idx) => (
        <Link
          href={`/features/${f.id}`}
          key={f.id}
          className="group relative block h-full w-full p-2"
          onMouseEnter={() => setHovered(idx)}
          onMouseLeave={() => setHovered(null)}
        >
          <AnimatePresence>
            {hovered === idx && (
              <motion.span
                className="bg-muted absolute inset-0 block h-full w-full rounded-2xl"
                layoutId="feature-hover"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1, transition: { duration: 0.15 } }}
                exit={{ opacity: 0, transition: { duration: 0.15, delay: 0.2 } }}
              />
            )}
          </AnimatePresence>
          <div className="bg-card border-border/60 group-hover:border-border relative z-20 flex h-full flex-col rounded-xl border p-5 transition-colors">
            <div className="flex items-start justify-between gap-2">
              <span className="text-muted-foreground font-mono text-xs tracking-wider">{f.key}</span>
              {f.status === "archived" ? (
                <Badge variant="outline">
                  <Archive className="mr-1 size-3" />
                  archived
                </Badge>
              ) : (
                <AccessBadge reason={f.access_reason} />
              )}
            </div>
            <h3 className="mt-2 font-medium">{f.name}</h3>
            <p className="text-muted-foreground mt-1 line-clamp-2 text-sm leading-relaxed">
              {f.description ?? "No description."}
            </p>
            <div className="text-muted-foreground mt-auto flex flex-wrap items-center gap-1.5 pt-4 text-xs">
              {f.teams.map((t) => (
                <Badge key={t.id} variant="secondary">
                  {t.name}
                </Badge>
              ))}
              <span className="ml-auto inline-flex items-center gap-1">
                <Users className="size-3.5" />
                {f.assignees.length}
              </span>
              <span>· {f.session_count} sessions</span>
            </div>
          </div>
        </Link>
      ))}
    </div>
  );
}
