"use client";
import { motion } from "framer-motion";

/**
 * Fades a route's content in on mount instead of letting Next.js swap it in
 * as a hard cut. Each admin tab is a separate page component (App Router
 * unmounts/remounts on navigation even within a shared layout), so without
 * this, clicking between Overview/Users/Usage/Settings/Audit reads as a
 * flicker - blank, then content - rather than a transition. Matches the
 * fade/slide the rest of the app already uses (see app/dashboard/page.tsx's
 * motion.header, app/login/page.tsx's card).
 */
export default function PageTransition({ children }: { children: React.ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  );
}
