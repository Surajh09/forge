"use client";

import { Button } from "@/components/ui/button";

export default function AppError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const apiDown = /fetch failed|ECONNREFUSED/i.test(error.message);
  return (
    <div className="border-destructive/30 bg-destructive/5 mx-auto mt-10 max-w-lg rounded-xl border p-6">
      <h2 className="font-medium">Something went wrong</h2>
      <p className="text-muted-foreground mt-2 text-sm">
        {apiDown
          ? "The Forge API is not reachable. Start it with `pnpm api` from the repo root (it listens on http://localhost:8000)."
          : error.message}
      </p>
      <Button className="mt-4" variant="outline" size="sm" onClick={reset}>
        Try again
      </Button>
    </div>
  );
}
