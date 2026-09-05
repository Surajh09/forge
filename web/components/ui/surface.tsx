import { cn } from "@/lib/utils";

/**
 * The one card treatment for Forge.
 *
 * Replaces three competing patterns that had drifted apart: shadcn's
 * `ring-1 ring-foreground/10`, the hand-rolled `border-border/60 rounded-xl
 * border` string (repeated verbatim in four files), and Aceternity's
 * `border-neutral-200 bg-white`.
 *
 * `tone` encodes the distinction the product rests on — session history is a
 * record of what happened, context is durable knowledge — so the two never
 * read as the same kind of thing.
 */

type SurfaceTone = "default" | "glass" | "knowledge" | "muted";

const TONE: Record<SurfaceTone, string> = {
  // Plain container: history, tables, neutral groupings.
  default: "bg-card border-border shadow-[var(--elevation-1)]",
  // Translucent, for anything layered over the gradient field.
  glass: "glass-surface shadow-[var(--elevation-2)]",
  // Durable knowledge: gradient edge and a brand-tinted border.
  knowledge:
    "bg-card border-primary/15 shadow-[var(--elevation-1)] before:pointer-events-none before:absolute before:inset-0 before:rounded-[inherit] before:bg-[var(--gradient-edge)] before:opacity-60",
  muted: "bg-muted/40 border-border/70",
};

const PAD = {
  none: "",
  sm: "p-3",
  md: "p-4",
  lg: "p-6",
} as const;

export function Surface({
  tone = "default",
  padding = "md",
  interactive = false,
  className,
  children,
  ...props
}: React.ComponentProps<"div"> & {
  tone?: SurfaceTone;
  padding?: keyof typeof PAD;
  interactive?: boolean;
}) {
  return (
    <div
      data-slot="surface"
      className={cn(
        "relative overflow-hidden rounded-xl border",
        TONE[tone],
        PAD[padding],
        interactive &&
          "hover:border-primary/30 hover:shadow-[var(--elevation-2)] transition-[border-color,box-shadow,transform] duration-200 hover:-translate-y-0.5",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

/**
 * Wrapper for full-bleed content such as tables.
 *
 * The previous inline version lacked `overflow-hidden`, so a table's own
 * horizontal scroll container rendered square corners inside the rounded
 * border and the first and last rows bled past the radius.
 */
export function SurfaceFrame({ className, children, ...props }: React.ComponentProps<"div">) {
  return (
    <Surface padding="none" className={cn("overflow-hidden", className)} {...props}>
      {children}
    </Surface>
  );
}
