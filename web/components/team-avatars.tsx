"use client";

import { AnimatedTooltip } from "@/components/ui/animated-tooltip";
import { avatarUrl } from "@/lib/format";
import type { User } from "@/lib/types";

/**
 * Aceternity animated tooltip over a row of avatars.
 *
 * `designation` is a plain string, not a callback: this is a client component and
 * server components cannot pass functions across the boundary. Omit it to fall
 * back to each user's role.
 */
export function TeamAvatars({ users, designation }: { users: User[]; designation?: string }) {
  if (users.length === 0) return <span className="text-muted-foreground text-sm">Nobody yet.</span>;
  const items = users.map((u, i) => ({
    id: i,
    name: u.display_name,
    designation: designation ?? u.role,
    image: avatarUrl(u),
  }));
  return (
    <div className="flex items-center pl-2">
      <AnimatedTooltip items={items} />
    </div>
  );
}
