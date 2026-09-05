import { cn } from "@/lib/utils";

/** Shimmer rather than a flat pulse, so loading reads as motion not a dead block. */
export function Skeleton({ className }: { className?: string }) {
  return (
    <div className={cn("bg-muted relative overflow-hidden rounded-md", className)}>
      <div className="absolute inset-0 -translate-x-full animate-[shimmer-sweep_1.6s_var(--ease-out-soft)_infinite] bg-gradient-to-r from-transparent via-white/25 to-transparent dark:via-white/10" />
    </div>
  );
}

function HeaderBlock() {
  return (
    <div className="mb-8 grid gap-2.5">
      <Skeleton className="h-3 w-24" />
      <Skeleton className="h-7 w-64" />
      <Skeleton className="h-4 w-96 max-w-full" />
    </div>
  );
}

/**
 * Loading shells shaped like the route they stand in for, so the page does not
 * reflow from a generic block layout into the real one.
 */
export function PageSkeleton({ variant = "list", rows = 5 }: { variant?: "list" | "grid" | "detail" | "stats"; rows?: number }) {
  return (
    <div>
      <HeaderBlock />

      {variant === "stats" && (
        <>
          <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-28 w-full rounded-xl" />
            ))}
          </div>
          <Skeleton className="h-64 w-full rounded-xl" />
        </>
      )}

      {variant === "grid" && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-40 w-full rounded-xl" />
          ))}
        </div>
      )}

      {variant === "detail" && (
        <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
          <div className="grid gap-4">
            <Skeleton className="h-56 w-full rounded-xl" />
            <Skeleton className="h-32 w-full rounded-xl" />
          </div>
          <Skeleton className="h-72 w-full rounded-xl" />
        </div>
      )}

      {variant === "list" && (
        <div className="border-border overflow-hidden rounded-xl border">
          {Array.from({ length: rows }).map((_, i) => (
            <div key={i} className="border-border/60 border-b p-4 last:border-b-0">
              <Skeleton className="h-4 w-1/3" />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
