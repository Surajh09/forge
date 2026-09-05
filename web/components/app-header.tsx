import Link from "next/link";
import { OrganizationSwitcher, UserButton } from "@clerk/nextjs";
import { auth } from "@clerk/nextjs/server";
import { Hammer } from "lucide-react";

import { NavLink } from "@/components/nav-link";
import { Button } from "@/components/ui/button";

// Clerk Core 3 removed <SignedIn>/<SignedOut>; this is a server component that
// already resolves the session, so it branches on userId directly.
export async function AppHeader() {
  const { userId, orgId, has } = await auth();
  const isAdmin = Boolean(userId && orgId && has({ role: "org:admin" }));

  const nav = [
    { href: "/dashboard", label: "Dashboard" },
    { href: "/features", label: "Features" },
    { href: "/sessions", label: "Sessions" },
    { href: "/search", label: "Search" },
    { href: "/review", label: "Review" },
    { href: "/agent", label: "Agent" },
    ...(isAdmin ? [{ href: "/admin", label: "Admin" }] : []),
  ];

  return (
    <header className="border-border/60 bg-background/80 sticky top-0 z-40 border-b backdrop-blur">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-6 px-4">
        <Link href={userId ? "/dashboard" : "/"} className="flex items-center gap-2 font-semibold tracking-tight">
          <span className="bg-primary text-primary-foreground flex size-7 items-center justify-center rounded-md">
            <Hammer className="size-4" />
          </span>
          Forge
        </Link>

        {userId && (
          <nav className="hidden items-center gap-1 text-sm sm:flex">
            {nav.map((item) => (
              <NavLink key={item.href} href={item.href} label={item.label} />
            ))}
          </nav>
        )}

        <div className="ml-auto flex items-center gap-3">
          {userId ? (
            <>
              <OrganizationSwitcher
                hidePersonal
                afterSelectOrganizationUrl="/dashboard"
                afterCreateOrganizationUrl="/dashboard"
                afterLeaveOrganizationUrl="/select-org"
              />
              <UserButton />
            </>
          ) : (
            <>
              <Button variant="ghost" size="sm" nativeButton={false} render={<Link href="/sign-in" />}>
                Sign in
              </Button>
              <Button size="sm" nativeButton={false} render={<Link href="/sign-up" />}>
                Get started
              </Button>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
