"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

/** Nav item with a current-route indicator — previously every link looked identical. */
export function NavLink({ href, label }: { href: string; label: string }) {
  const pathname = usePathname();
  const active = pathname === href || pathname.startsWith(`${href}/`);

  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "relative rounded-md px-2.5 py-1.5 transition-colors",
        active ? "text-foreground" : "text-muted-foreground hover:text-foreground hover:bg-muted",
      )}
    >
      {label}
      {active && (
        <span className="bg-[image:var(--gradient-accent)] absolute inset-x-2.5 -bottom-[11px] h-0.5 rounded-full" />
      )}
    </Link>
  );
}
