"use client";

import type { ReactNode } from "react";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Radio, TrendingUp } from "lucide-react";
import BrandHeading from "./BrandHeading";
import UserMenu from "./UserMenu";
import { NavLink } from "./HeaderNav";

/**
 * The one header every signed-in page renders.
 *
 * Five pages used to hand-roll this block, each with a slightly different
 * nav list, and each wrapped in `flex-wrap` — so on the dashboard, where the
 * row also carries three selectors, a status pill and an action button, the
 * navigation fell onto a second line and the header grew to twice its height.
 *
 * The fix is structural rather than cosmetic:
 *
 *   1. Navigation is the three *places* you can go. Account, Admin and Sign
 *      out moved into <UserMenu/>, which is one control instead of three.
 *   2. The row is `flex-nowrap` from `lg` up, and the middle zone is the one
 *      allowed to shrink (`min-w-0` + horizontal scroll) — so when something
 *      has to give at an awkward width, it's the selectors that scroll, not
 *      the whole bar that reflows.
 *   3. Below `lg` it wraps deliberately, because a phone has no room for one
 *      line and pretending otherwise just produces a squashed, unreadable bar.
 *
 * `controls` is the page's own context (build/project pickers, "New Build"),
 * rendered between the nav and the account menu.
 */

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/runs/live", label: "Live Runs", icon: Radio },
  { href: "/build-trends", label: "Build Trends", icon: TrendingUp },
];

/**
 * How much navigation a page shows.
 *
 * "full"  — the dashboard, the hub you arrive at after signing in.
 * "home"  — Live Runs and Build Trends: one way back to the dashboard, which
 *           is the only move that makes sense from a leaf page.
 * "none"  — Admin console and Account. These are entered deliberately from
 *           the account menu and leave by the "Back to dashboard" link in
 *           their own subtitle; listing Live Runs next to User Management
 *           put two unrelated levels of the app in one strip.
 */
export type NavScope = "full" | "home" | "none";

const NAV_BY_SCOPE: Record<NavScope, typeof NAV> = {
  full: NAV,
  home: NAV.slice(0, 1),
  none: [],
};

export default function AppHeader({
  label,
  subtitle,
  controls,
  maxWidth = "max-w-[1600px]",
  nav = "full",
  locked = false,
  below,
}: {
  /** Page name shown after the wordmark. */
  label?: string;
  /** Replaces the tagline under the wordmark (e.g. a "back" link). */
  subtitle?: ReactNode;
  /** Page-specific context controls, right of the nav. */
  controls?: ReactNode;
  /** Match the page's own content width so the header lines up with it. */
  maxWidth?: string;
  /** How much navigation this page shows — see NavScope. */
  nav?: NavScope;
  /** True while a forced password change is pending: reduces the account
   *  menu to identity + sign out, because every other route 403s until the
   *  password is set. */
  locked?: boolean;
  /** A second row inside the same sticky element — used by the admin console
   *  for its section tabs. Rendering it here rather than as a sibling below
   *  the header is what lets it stick correctly without hardcoding the
   *  header's pixel height as a `top-[57px]` offset that silently breaks the
   *  moment the header's padding or logo size changes. */
  below?: ReactNode;
}) {
  const pathname = usePathname();
  const navItems = locked ? [] : NAV_BY_SCOPE[nav];
  const isActive = (href: string) =>
    href === "/dashboard" ? pathname === href : pathname.startsWith(href);

  return (
    <header className="sticky top-0 z-50 border-b border-slate-200 bg-white/90 shadow-[0_4px_30px_rgba(15,23,42,0.08)] backdrop-blur-xl dark:border-white/[0.06] dark:bg-black/80 dark:shadow-[0_4px_30px_rgba(0,0,0,0.5)]">
      <div
        className={`mx-auto flex ${maxWidth} flex-wrap items-center gap-x-4 gap-y-3 px-4 py-2.5 sm:px-6 lg:flex-nowrap`}
      >
        <BrandHeading label={label} subtitle={subtitle} />

        {navItems.length > 0 && (
          <nav className="order-3 flex shrink-0 items-center gap-1 lg:order-none">
            {navItems.map((item) => (
              <NavLink
                key={item.href}
                href={item.href}
                icon={item.icon}
                label={item.label}
                active={isActive(item.href)}
              />
            ))}
          </nav>
        )}

        {/* The flexible middle. `min-w-0` is what lets it actually shrink
            instead of forcing the row wider than the viewport, and the
            scrollbar is hidden because a visible one inside a 44px-tall
            header reads as a rendering glitch. */}
        <div className="order-4 min-w-0 flex-1 lg:order-none">
          {controls && (
            <div className="no-scrollbar flex items-center justify-end gap-2 overflow-x-auto">
              {controls}
            </div>
          )}
        </div>

        <div className="order-2 ml-auto shrink-0 lg:order-none lg:ml-0">
          <UserMenu locked={locked} />
        </div>
      </div>

      {below && (
        <div className="border-t border-slate-200 dark:border-white/[0.06]">
          <div className={`mx-auto ${maxWidth} px-4 sm:px-6`}>{below}</div>
        </div>
      )}
    </header>
  );
}
