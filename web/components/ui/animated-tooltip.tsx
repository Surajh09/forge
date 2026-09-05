"use client";

import React, { useState, useRef } from "react";
import {
  motion,
  useTransform,
  AnimatePresence,
  useMotionValue,
  useSpring,
} from "motion/react";

export const AnimatedTooltip = ({
  items,
}: {
  items: {
    id: number;
    name: string;
    designation: string;
    image: string;
  }[];
}) => {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const springConfig = { stiffness: 100, damping: 15 };
  const x = useMotionValue(0);
  const animationFrameRef = useRef<number | null>(null);

  const rotate = useSpring(
    useTransform(x, [-100, 100], [-45, 45]),
    springConfig,
  );
  const translateX = useSpring(
    useTransform(x, [-100, 100], [-50, 50]),
    springConfig,
  );

  const handleMouseMove = (event: React.MouseEvent<HTMLImageElement>) => {
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
    }

    const halfWidth = event.currentTarget.offsetWidth / 2;
    const offsetX = event.nativeEvent.offsetX;
    animationFrameRef.current = requestAnimationFrame(() => {
      x.set(offsetX - halfWidth);
    });
  };

  return (
    <>
      {items.map((item) => (
        <div
          className="group relative -mr-2"
          key={item.name}
          onMouseEnter={() => setHoveredIndex(item.id)}
          onMouseLeave={() => setHoveredIndex(null)}
        >
          <AnimatePresence>
            {hoveredIndex === item.id && (
              <motion.div
                initial={{ opacity: 0, y: 20, scale: 0.6 }}
                animate={{
                  opacity: 1,
                  y: 0,
                  scale: 1,
                  transition: {
                    type: "spring",
                    stiffness: 260,
                    damping: 10,
                  },
                }}
                exit={{ opacity: 0, y: 20, scale: 0.6 }}
                style={{
                  translateX: translateX,
                  rotate: rotate,
                  whiteSpace: "nowrap",
                }}
                className="bg-popover text-popover-foreground border-border absolute -top-14 left-1/2 z-50 flex -translate-x-1/2 flex-col items-center justify-center rounded-lg border px-3 py-1.5 text-xs shadow-[var(--elevation-2)]"
              >
                <div className="absolute inset-x-8 -bottom-px z-30 h-px bg-[image:var(--gradient-accent)]" />
                <div className="relative z-30 text-sm font-medium">{item.name}</div>
                <div className="text-muted-foreground text-xs">{item.designation}</div>
              </motion.div>
            )}
          </AnimatePresence>
          {/* eslint-disable-next-line @next/next/no-img-element -- external avatar URLs, no optimization needed */}
          <img
            onMouseMove={handleMouseMove}
            height={100}
            width={100}
            src={item.image}
            alt={item.name}
            // 28px, not 56px: these sit inline in a text-sm metadata row beside
            // 20px badges, where a 56px stack dwarfed everything around it.
            className="border-background relative !m-0 size-7 rounded-full border-2 object-cover object-top !p-0 transition duration-500 group-hover:z-30 group-hover:scale-110"
          />
        </div>
      ))}
    </>
  );
};
