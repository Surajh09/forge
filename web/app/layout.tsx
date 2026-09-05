import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import { Geist, Geist_Mono } from "next/font/google";

import { AppHeader } from "@/components/app-header";

import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Forge",
  description: "Shared engineering context for developers and coding agents.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      {/*
        suppressHydrationWarning: browser extensions (ColorZilla's `cz-shortcut-listen`,
        Grammarly, password managers) add attributes to <body> before React hydrates, which
        React reports as a mismatch. This suppresses that one element's own attributes only —
        real mismatches inside the tree are still reported.
      */}
      <body
        className="bg-background text-foreground flex min-h-full flex-col font-sans"
        suppressHydrationWarning
      >
        <ClerkProvider>
          <AppHeader />
          {children}
        </ClerkProvider>
      </body>
    </html>
  );
}
