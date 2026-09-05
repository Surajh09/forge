import Link from "next/link";
import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import { ArrowRight, Database, ShieldCheck, Users } from "lucide-react";

import { BackgroundBeams } from "@/components/ui/background-beams";
import { Button } from "@/components/ui/button";
import { Surface } from "@/components/ui/surface";

const pillars = [
  {
    icon: ShieldCheck,
    title: "Feature is the boundary",
    body: "Access to sessions and context follows the feature: assigned to it, or on a team that owns it. Never org-wide by default.",
  },
  {
    icon: Database,
    title: "One Context Bank",
    body: "Every completed session writes validated, versioned context with provenance. Local stores are caches, never the truth.",
  },
  {
    icon: Users,
    title: "Humans and agents, same rules",
    body: "Claude and other coding agents will operate inside the exact authorization scope of the developer who started them.",
  },
];

export default async function LandingPage() {
  const { userId } = await auth();
  if (userId) redirect("/dashboard");

  return (
    <main className="flex flex-1 flex-col">
      {/* One continuous surface: the hero gradient fades into the page rather
          than meeting it at a hard black-to-white seam. */}
      <section className="relative flex min-h-[72vh] flex-col items-center justify-center overflow-hidden px-6 py-24">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 -z-10 bg-[image:var(--gradient-hero)]"
        />
        <div
          aria-hidden
          className="from-background pointer-events-none absolute inset-x-0 bottom-0 -z-10 h-40 bg-gradient-to-t to-transparent"
        />
        <BackgroundBeams className="pointer-events-none -z-10 opacity-40" />

        <div className="relative z-10 mx-auto max-w-3xl text-center">
          <p className="text-muted-foreground mb-4 font-mono text-caption uppercase">Forge</p>
          <h1 className="text-display font-semibold text-balance">
            Shared engineering context for{" "}
            <span className="gradient-text">developers and coding agents</span>
          </h1>
          <p className="text-muted-foreground mx-auto mt-6 max-w-xl text-base text-pretty sm:text-lg">
            Stop duplicating work. Forge keeps every feature&apos;s decisions, constraints and open questions in one
            place — visible to exactly the people and agents who should see them.
          </p>
          <div className="mt-10 flex items-center justify-center gap-3">
            <Button size="lg" nativeButton={false} render={<Link href="/sign-up" />}>
              Get started
              <ArrowRight data-icon="inline-end" />
            </Button>
            <Button size="lg" variant="outline" nativeButton={false} render={<Link href="/sign-in" />}>
              Sign in
            </Button>
          </div>
        </div>
      </section>

      <section className="mx-auto grid w-full max-w-6xl gap-4 px-6 pb-24 sm:grid-cols-3">
        {pillars.map(({ icon: Icon, title, body }) => (
          <Surface key={title} tone="knowledge" padding="lg" interactive>
            <div className="bg-primary/10 text-primary mb-4 flex size-9 items-center justify-center rounded-lg">
              <Icon className="size-4.5" />
            </div>
            <h2 className="text-section font-medium">{title}</h2>
            <p className="text-muted-foreground mt-2 text-sm leading-relaxed">{body}</p>
          </Surface>
        ))}
      </section>
    </main>
  );
}
