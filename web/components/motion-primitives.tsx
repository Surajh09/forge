"use client";

import { motion, useReducedMotion } from "motion/react";

import { cn } from "@/lib/utils";

const EASE = [0.22, 1, 0.36, 1] as const;

/** Entrance animation that respects the OS reduced-motion setting. */
export function FadeIn({
  delay = 0,
  y = 8,
  className,
  children,
}: {
  delay?: number;
  y?: number;
  className?: string;
  children: React.ReactNode;
}) {
  const reduced = useReducedMotion();
  if (reduced) return <div className={className}>{children}</div>;

  return (
    <motion.div
      initial={{ opacity: 0, y }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay, ease: EASE }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

/** Staggers direct children on mount. Children must be Stagger.Item. */
export function Stagger({
  className,
  gap = 0.05,
  children,
}: {
  className?: string;
  gap?: number;
  children: React.ReactNode;
}) {
  const reduced = useReducedMotion();
  if (reduced) return <div className={className}>{children}</div>;

  return (
    <motion.div
      className={className}
      initial="hidden"
      animate="show"
      variants={{ hidden: {}, show: { transition: { staggerChildren: gap } } }}
    >
      {children}
    </motion.div>
  );
}

Stagger.Item = function StaggerItem({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <motion.div
      className={className}
      variants={{
        hidden: { opacity: 0, y: 10 },
        show: { opacity: 1, y: 0, transition: { duration: 0.35, ease: EASE } },
      }}
    >
      {children}
    </motion.div>
  );
};

/** Subtle lift on hover for clickable surfaces. */
export function Lift({ className, children }: { className?: string; children: React.ReactNode }) {
  const reduced = useReducedMotion();
  if (reduced) return <div className={className}>{children}</div>;

  return (
    <motion.div
      className={cn(className)}
      whileHover={{ y: -2 }}
      transition={{ duration: 0.2, ease: EASE }}
    >
      {children}
    </motion.div>
  );
}
