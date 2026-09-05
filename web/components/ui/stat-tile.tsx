import Link from "next/link";

import { Surface } from "@/components/ui/surface";
import { cn } from "@/lib/utils";

/** Number over label, for counts that deserve weight. */
export function StatTile({
  value,
  label,
  hint,
  icon,
  href,
  accent = false,
  className,
}: {
  value: React.ReactNode;
  label: string;
  hint?: React.ReactNode;
  icon?: React.ReactNode;
  href?: string;
  accent?: boolean;
  className?: string;
}) {
  const body = (
    <Surface
      tone={accent ? "knowledge" : "default"}
      interactive={Boolean(href)}
      className={cn("h-full", className)}
    >
      <div className="relative flex items-start justify-between gap-3">
        <div>
          <div
            className={cn(
              "text-3xl font-semibold tabular-nums tracking-tight",
              accent && "gradient-text",
            )}
          >
            {value}
          </div>
          <div className="text-muted-foreground mt-1 text-sm">{label}</div>
          {hint && <div className="text-muted-foreground mt-2 text-xs">{hint}</div>}
        </div>
        {icon && <span className="text-muted-foreground shrink-0">{icon}</span>}
      </div>
    </Surface>
  );

  return href ? (
    <Link href={href} className="block">
      {body}
    </Link>
  ) : (
    body
  );
}

export function StatRow({ className, children }: { className?: string; children: React.ReactNode }) {
  return <div className={cn("grid gap-3 sm:grid-cols-2 lg:grid-cols-3", className)}>{children}</div>;
}
