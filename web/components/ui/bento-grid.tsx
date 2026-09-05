import { cn } from "@/lib/utils";

export const BentoGrid = ({
  className,
  children,
}: {
  className?: string;
  children?: React.ReactNode;
}) => {
  return (
    <div
      className={cn(
        "mx-auto grid max-w-7xl grid-cols-1 gap-4 md:auto-rows-[18rem] md:grid-cols-3",
        className,
      )}
    >
      {children}
    </div>
  );
};

export const BentoGridItem = ({
  className,
  title,
  description,
  header,
  icon,
}: {
  className?: string;
  title?: string | React.ReactNode;
  description?: string | React.ReactNode;
  header?: React.ReactNode;
  icon?: React.ReactNode;
}) => {
  return (
    <div
      className={cn(
        // Converted to Forge tokens. Was: neutral-200/white/black with an
        // undefined `shadow-input` utility, and title/description both
        // text-neutral-600 — identical colour, so weight carried all hierarchy.
        "group/bento border-border bg-card row-span-1 flex flex-col justify-between space-y-4 rounded-xl border p-4 shadow-[var(--elevation-1)] transition duration-200 hover:shadow-[var(--elevation-2)]",
        className,
      )}
    >
      {header}
      <div className="transition duration-200 group-hover/bento:translate-x-1">
        {icon}
        <div className="text-foreground mt-2 mb-2 font-sans font-medium">{title}</div>
        <div className="text-muted-foreground font-sans text-xs font-normal">{description}</div>
      </div>
    </div>
  );
};
