"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import {
  ChevronDown,
  KeyRound,
  LogOut,
  ScrollText,
  Settings as SettingsIcon,
  Shield,
  UserCog,
  Users,
} from "lucide-react";
import { usePermissions } from "@/lib/usePermissions";
import { formatRoleLabel } from "@/lib/roles";

/**
 * The account menu in the top-right of every signed-in page.
 *
 * It exists to take Account, Admin and Logout *out* of the navigation bar.
 * Those three were rendered as peer links next to Dashboard / Live Runs /
 * Build Trends, which is what pushed the dashboard header onto a second row:
 * six nav items plus three selectors plus a status pill cannot share a line.
 * They also aren't navigation in the same sense — nobody moves between
 * "Build Trends" and "Logout" — so grouping them under the signed-in
 * identity is both smaller and truer to what they are.
 *
 * Everything below the divider is gated on real permissions from
 * /auth/permissions, not on a role-name comparison: an SDET sees two items,
 * an admin sees six, and adding a role to services/permissions.py is enough
 * to make this menu correct for it without touching this file.
 */

type MenuItem = {
  href: string;
  label: string;
  icon: typeof UserCog;
  /** Undefined = everyone signed in. Otherwise the permission required. */
  permission?: string;
};

const ACCOUNT_ITEMS: MenuItem[] = [
  { href: "/account", label: "Account settings", icon: UserCog },
];

const ADMIN_ITEMS: MenuItem[] = [
  { href: "/admin", label: "Admin console", icon: Shield, permission: "users.manage" },
  { href: "/admin/users", label: "User management", icon: Users, permission: "users.manage" },
  { href: "/admin/usage", label: "Usage & tokens", icon: KeyRound, permission: "usage.view_all" },
  { href: "/admin/settings", label: "LLM settings", icon: SettingsIcon, permission: "settings.manage" },
  { href: "/admin/audit", label: "Audit log", icon: ScrollText, permission: "audit.view" },
];

/** Up to two letters, from a full name if we have one, else the username. */
function initialsFor(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
}

/** The username is written once at login and never mutates in place, so
 *  there is nothing to subscribe to — the store contract still wants a
 *  subscribe function, and a stable no-op is the correct one. */
function subscribeToNothing() {
  return () => {};
}

function readStoredUsername(): string {
  return localStorage.getItem("username") || "";
}

function readServerUsername(): string {
  return "";
}

export default function UserMenu({ locked = false }: { locked?: boolean }) {
  const { permissions, loaded, has } = usePermissions();
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  // localStorage is the instant source (written at login) and the API
  // response is the authoritative one; reading both means the avatar has a
  // name on first paint instead of popping in a beat later. Read through
  // useSyncExternalStore rather than an effect so the prerendered HTML and
  // the first client render agree (server snapshot "") instead of
  // hydrating with a name the server never wrote.
  const storedName = useSyncExternalStore(subscribeToNothing, readStoredUsername, readServerUsername);

  const username = permissions.username || storedName;
  const displayName = permissions.full_name || username || "Signed in";
  const roleLabel = formatRoleLabel(permissions.role || "");
  const workspace = permissions.workspace_id || "";

  useEffect(() => {
    if (!open) return;
    const onClickOutside = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onClickOutside);
    document.addEventListener("keydown", onEscape);
    return () => {
      document.removeEventListener("mousedown", onClickOutside);
      document.removeEventListener("keydown", onEscape);
    };
  }, [open]);

  const handleLogout = useCallback(() => {
    localStorage.clear();
    window.location.href = "/";
  }, []);

  // `has` is optimistic until /auth/permissions resolves, which is right for
  // hiding a button you'd otherwise see flicker — but wrong here, where it
  // would briefly show an SDET the whole admin section. Wait for the real
  // answer before drawing gated rows.
  //
  // `locked` is a forced password change: credential_change_middleware 403s
  // every route except the account one, so offering links to them would be
  // offering dead ends. Sign out stays — it is the one way out of a locked
  // session that isn't setting the password.
  const adminItems = loaded && !locked ? ADMIN_ITEMS.filter((item) => has(item.permission!)) : [];
  const accountItems = locked ? [] : ACCOUNT_ITEMS;

  return (
    <div ref={boxRef} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex items-center gap-2 rounded-full border border-slate-200 bg-white py-1 pl-1 pr-2 transition-colors hover:border-cyan-500/30 hover:bg-slate-50 dark:border-white/[0.08] dark:bg-white/[0.03] dark:hover:border-cyan-500/25 dark:hover:bg-white/[0.06]"
      >
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-cyan-500 to-blue-600 text-[11px] font-bold text-white">
          {initialsFor(displayName)}
        </span>
        <span className="hidden min-w-0 text-left leading-tight sm:block">
          <span className="block max-w-[120px] truncate text-xs font-semibold text-slate-800 dark:text-white/85">
            {displayName}
          </span>
          {roleLabel && (
            <span className="block text-[10px] font-medium text-slate-500 dark:text-white/40">
              {roleLabel}
            </span>
          )}
        </span>
        <ChevronDown
          className={`h-3.5 w-3.5 shrink-0 text-slate-400 transition-transform dark:text-white/30 ${
            open ? "rotate-180" : ""
          }`}
        />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -6, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.97 }}
            transition={{ duration: 0.14 }}
            role="menu"
            className="absolute right-0 z-50 mt-2 w-64 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-[0_10px_40px_rgba(15,23,42,0.14)] dark:border-white/[0.08] dark:bg-[#0b0b0b] dark:shadow-[0_10px_40px_rgba(0,0,0,0.7)]"
          >
            {/* Who you are signed in as — the question the menu answers first. */}
            <div className="flex items-center gap-3 border-b border-slate-200 bg-slate-50 px-4 py-3 dark:border-white/[0.06] dark:bg-white/[0.02]">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-cyan-500 to-blue-600 text-xs font-bold text-white">
                {initialsFor(displayName)}
              </span>
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-slate-900 dark:text-white">
                  {displayName}
                </p>
                <p className="mt-0.5 flex flex-wrap items-center gap-1 text-[10px]">
                  {roleLabel && (
                    <span className="rounded-full border border-cyan-500/25 bg-cyan-500/10 px-1.5 py-0.5 font-bold text-cyan-700 dark:text-cyan-300">
                      {roleLabel}
                    </span>
                  )}
                  {workspace && (
                    <span className="max-w-[110px] truncate text-slate-500 dark:text-white/35">
                      {workspace}
                    </span>
                  )}
                </p>
              </div>
            </div>

            {accountItems.length > 0 && (
              <div className="py-1">
                {accountItems.map((item) => (
                  <MenuLink key={item.href} item={item} onNavigate={() => setOpen(false)} />
                ))}
              </div>
            )}

            {adminItems.length > 0 && (
              <div className="border-t border-slate-200 py-1 dark:border-white/[0.06]">
                <p className="px-4 pb-1 pt-2 text-[10px] font-bold uppercase tracking-widest text-slate-400 dark:text-white/25">
                  Administration
                </p>
                {adminItems.map((item) => (
                  <MenuLink key={item.href} item={item} onNavigate={() => setOpen(false)} />
                ))}
              </div>
            )}

            <div className="border-t border-slate-200 py-1 dark:border-white/[0.06]">
              <button
                role="menuitem"
                onClick={handleLogout}
                className="flex w-full items-center gap-2.5 px-4 py-2 text-left text-sm text-slate-600 transition-colors hover:bg-red-50 hover:text-red-600 dark:text-white/60 dark:hover:bg-red-500/[0.1] dark:hover:text-red-400"
              >
                <LogOut className="h-4 w-4 shrink-0" />
                Sign out
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function MenuLink({ item, onNavigate }: { item: MenuItem; onNavigate: () => void }) {
  const Icon = item.icon;
  return (
    <Link
      role="menuitem"
      href={item.href}
      onClick={onNavigate}
      className="flex items-center gap-2.5 px-4 py-2 text-sm text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900 dark:text-white/60 dark:hover:bg-white/[0.06] dark:hover:text-white"
    >
      <Icon className="h-4 w-4 shrink-0" />
      {item.label}
    </Link>
  );
}
