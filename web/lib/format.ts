export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.round(diff / 60_000);
  if (Math.abs(minutes) < 1) return "just now";
  if (Math.abs(minutes) < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (Math.abs(days) < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

export function formatDuration(start: string, end: string | null): string {
  if (!end) return "running";
  const minutes = Math.max(1, Math.round((new Date(end).getTime() - new Date(start).getTime()) / 60_000));
  if (minutes < 60) return `${minutes}m`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m ? `${h}h ${m}m` : `${h}h`;
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}

export function titleCase(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Deterministic avatar for users without an image (demo users). */
export function avatarUrl(user: { avatar_url: string | null; display_name: string; id: string }): string {
  if (user.avatar_url) return user.avatar_url;
  const seed = encodeURIComponent(user.id);
  return `https://api.dicebear.com/9.x/initials/svg?seed=${seed}&backgroundType=gradientLinear`;
}
