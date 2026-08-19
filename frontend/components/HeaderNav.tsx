"use client";

import Link from "next/link";
import type { ComponentType } from "react";

/**
 * The one nav style every Sentinel header uses.
 *
 * Every header link used to pick its own hue — Live Runs emerald, Build
 * Trends cyan, Admin purple, Account slate, Logout red — so the top of the
 * app read as five unrelated buttons rather than one navigation bar. A
 * production header does the opposite: one neutral resting state, one accent
 * reserved for the current page, and colour used only where it carries
 * meaning (destructive actions, live status).
 */

const BASE =
  "flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold transition-all active:scale-95";

/** Not the current page: neutral, no hue of its own. */
export const NAV_IDLE =
  `${BASE} border-transparent text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-white/55 dark:hover:bg-white/[0.06] dark:hover:text-white`;

/** The page you are on. Cyan is the brand accent and is reserved for this. */
export const NAV_ACTIVE =
  `${BASE} border-cyan-500/25 bg-cyan-500/10 text-cyan-600 dark:text-cyan-400`;

/** A bordered action that is not navigation (e.g. "Add New Build"). */
export const NAV_ACTION =
  `${BASE} border-slate-300 bg-slate-100 text-slate-700 hover:bg-slate-200 dark:border-white/[0.1] dark:bg-white/[0.05] dark:text-white/75 dark:hover:bg-white/[0.1]`;

/** Destructive. The only place red is allowed in a header. */
export const NAV_DANGER =
  `${BASE} border-transparent text-slate-600 hover:bg-red-50 hover:text-red-600 dark:text-white/55 dark:hover:bg-red-500/[0.1] dark:hover:text-red-400`;

export function NavLink({
  href,
  icon: Icon,
  label,
  active = false,
}: {
  href: string;
  icon: ComponentType<{ className?: string }>;
  label: string;
  active?: boolean;
}) {
  return (
    <Link href={href} className={active ? NAV_ACTIVE : NAV_IDLE} aria-current={active ? "page" : undefined}>
      <Icon className="h-3.5 w-3.5" />
      {label}
    </Link>
  );
}
