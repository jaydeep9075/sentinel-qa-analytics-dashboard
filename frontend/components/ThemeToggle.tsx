"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Moon, Sun } from "lucide-react";
import { useTheme } from "@/lib/theme";

export default function ThemeToggle() {
  const { isDark, toggleTheme } = useTheme();
  const [ripples, setRipples] = useState<number[]>([]);

  const handleClick = () => {
    const id = Date.now();
    setRipples((prev) => [...prev, id]);
    // Ripple only needs to live long enough to play its exit animation.
    setTimeout(() => setRipples((prev) => prev.filter((r) => r !== id)), 600);
    toggleTheme();
  };

  return (
    <motion.button
      onClick={handleClick}
      initial={{ opacity: 0, y: 16, scale: 0.8 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: "spring", stiffness: 260, damping: 20, delay: 0.3 }}
      whileHover={{ scale: 1.08, y: -2 }}
      whileTap={{ scale: 0.92 }}
      className="fixed bottom-44 right-6 z-[70] flex h-11 w-11 items-center justify-center overflow-hidden rounded-full border border-slate-300 bg-white/90 text-slate-700 shadow-[0_4px_20px_rgba(15,23,42,0.12)] backdrop-blur transition-colors hover:border-cyan-500/40 hover:text-cyan-600 dark:border-white/10 dark:bg-black/70 dark:text-white/70 dark:shadow-[0_4px_25px_rgba(0,0,0,0.5)] dark:hover:border-cyan-400/30 dark:hover:text-cyan-300"
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
      title={isDark ? "Switch to light mode" : "Switch to dark mode"}
    >
      {/* Slow breathing glow ring so the button reads as "alive" even at rest */}
      <motion.span
        aria-hidden
        className="pointer-events-none absolute inset-0 rounded-full bg-cyan-400/25"
        animate={{ scale: [1, 1.35, 1], opacity: [0.5, 0, 0.5] }}
        transition={{ duration: 2.8, repeat: Infinity, ease: "easeInOut" }}
      />

      {/* Click ripple */}
      <AnimatePresence>
        {ripples.map((id) => (
          <motion.span
            key={id}
            initial={{ scale: 0, opacity: 0.45 }}
            animate={{ scale: 2.4, opacity: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.6, ease: "easeOut" }}
            className="pointer-events-none absolute inset-0 rounded-full bg-cyan-400/50"
          />
        ))}
      </AnimatePresence>

      <AnimatePresence mode="wait" initial={false}>
        {isDark ? (
          <motion.span
            key="sun"
            initial={{ rotate: -90, opacity: 0, scale: 0.4 }}
            animate={{ rotate: 0, opacity: 1, scale: 1 }}
            exit={{ rotate: 90, opacity: 0, scale: 0.4 }}
            transition={{ type: "spring", stiffness: 300, damping: 22 }}
            className="relative flex items-center justify-center"
          >
            <Sun className="h-[18px] w-[18px]" />
          </motion.span>
        ) : (
          <motion.span
            key="moon"
            initial={{ rotate: 90, opacity: 0, scale: 0.4 }}
            animate={{ rotate: 0, opacity: 1, scale: 1 }}
            exit={{ rotate: -90, opacity: 0, scale: 0.4 }}
            transition={{ type: "spring", stiffness: 300, damping: 22 }}
            className="relative flex items-center justify-center"
          >
            <Moon className="h-[18px] w-[18px]" />
          </motion.span>
        )}
      </AnimatePresence>
    </motion.button>
  );
}
