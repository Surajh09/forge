import { cn } from "@/lib/utils";

/**
 * Every app page uses this, so the gradient field is applied here once rather
 * than per page. The gradient sits behind the header and fades out, giving the
 * app shell depth without each screen opting in.
 */
export function PageHeader({
  title,
  description,
  eyebrow,
  actions,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  eyebrow?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="relative mb-8">
      <div
        aria-hidden
        className="pointer-events-none absolute -inset-x-8 -top-24 -bottom-8 -z-10 bg-[image:var(--gradient-hero)]"
      />
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          {eyebrow && (
            <div className="text-muted-foreground mb-1.5 font-mono text-caption uppercase">{eyebrow}</div>
          )}
          <h1 className="text-title font-semibold">{title}</h1>
          {description && <p className="text-muted-foreground mt-2 max-w-2xl text-sm">{description}</p>}
        </div>
        {actions && <div className="flex items-center gap-2">{actions}</div>}
      </div>
    </div>
  );
}

/** Section heading, so h2s stop being re-typed with slightly different classes. */
export function SectionHeader({
  title,
  description,
  actions,
  className,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("mb-3 flex flex-wrap items-end justify-between gap-3", className)}>
      <div>
        <h2 className="text-section font-medium">{title}</h2>
        {description && <p className="text-muted-foreground mt-0.5 text-sm">{description}</p>}
      </div>
      {actions}
    </div>
  );
}

export function EmptyState({
  title,
  body,
  action,
  icon,
}: {
  title: string;
  body?: React.ReactNode;
  action?: React.ReactNode;
  icon?: React.ReactNode;
}) {
  return (
    <div className="border-border/70 bg-muted/25 relative overflow-hidden rounded-xl border border-dashed px-6 py-12 text-center">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[image:var(--gradient-hero)] opacity-50"
      />
      <div className="relative">
        {icon && (
          <div className="bg-card text-muted-foreground border-border mx-auto mb-4 flex size-11 items-center justify-center rounded-full border shadow-[var(--elevation-1)]">
            {icon}
          </div>
        )}
        <p className="font-medium">{title}</p>
        {body && <p className="text-muted-foreground mx-auto mt-1.5 max-w-md text-sm">{body}</p>}
        {action && <div className="mt-5 flex justify-center">{action}</div>}
      </div>
    </div>
  );
}
