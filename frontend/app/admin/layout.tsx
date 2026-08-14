"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Bell, Gauge, KeyRound, ScrollText, Settings as SettingsIcon, Users } from "lucide-react";
import BrandLogo from "@/components/BrandLogo";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function authHeaders(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

const TABS = [
  { href: "/admin", label: "Overview", icon: Gauge },
  { href: "/admin/users", label: "Users", icon: Users },
  { href: "/admin/usage", label: "Usage", icon: KeyRound },
  { href: "/admin/settings", label: "Settings", icon: SettingsIcon },
  { href: "/admin/audit", label: "Audit", icon: ScrollText },
];

type NotificationItem = {
  type: string;
  id: string;
  message: string;
  timestamp: string;
  link: string;
};

const NOTIF_POLL_MS = 60000;

function NotificationBell() {
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${API}/admin/notifications`, { headers: authHeaders() });
      if (!res.ok) return;
      const data = await res.json();
      setItems(data.items || []);
    } catch {
      // Silent - a failed background poll shouldn't put an error banner in
      // front of an admin who's looking at something else entirely.
    }
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, NOTIF_POLL_MS);
    return () => clearInterval(interval);
  }, [load]);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  return (
    <div className="relative" ref={boxRef}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative flex items-center justify-center w-9 h-9 rounded-lg border border-slate-200 dark:border-white/10 text-slate-500 dark:text-white/50 hover:text-cyan-500 hover:border-cyan-500/40"
        title="Notifications"
      >
        <Bell className="w-4 h-4" />
        {items.length > 0 && (
          <span className="absolute -top-1.5 -right-1.5 min-w-[18px] h-[18px] px-1 flex items-center justify-center rounded-full bg-red-500 text-white text-[10px] font-bold">
            {items.length > 99 ? "99+" : items.length}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-80 max-h-96 overflow-y-auto rounded-xl border border-slate-200 dark:border-white/[0.08] bg-white dark:bg-black/95 shadow-xl backdrop-blur-xl z-50">
          <div className="px-4 py-3 border-b border-slate-200 dark:border-white/[0.08] text-xs font-semibold uppercase tracking-widest text-slate-500 dark:text-white/40">
            Notifications
          </div>
          {items.length === 0 ? (
            <div className="px-4 py-6 text-sm text-slate-500 dark:text-white/40 text-center">Nothing needs your attention.</div>
          ) : (
            <ul>
              {items.map((item) => (
                <li key={item.id} className="border-b border-slate-100 dark:border-white/[0.04] last:border-0">
                  <Link
                    href={item.link}
                    onClick={() => setOpen(false)}
                    className="block px-4 py-3 text-sm hover:bg-slate-50 dark:hover:bg-white/[0.04]"
                  >
                    <p className="text-slate-800 dark:text-white/80">{item.message}</p>
                    {item.timestamp && (
                      <p className="mt-1 text-[10px] text-slate-400 dark:text-white/30">
                        {new Date(item.timestamp).toLocaleString()}
                      </p>
                    )}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [checking, setChecking] = useState(true);
  const [allowed, setAllowed] = useState(false);
  const [denyReason, setDenyReason] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!localStorage.getItem("token")) {
        router.push("/login");
        return;
      }
      try {
        const res = await fetch(`${API}/auth/me`, { headers: authHeaders() });
        if (res.status === 401) {
          router.push("/login");
          return;
        }
        const me = await res.json();
        if (cancelled) return;
        // A must-change-password session is refused by every backend route
        // except the handful credential_change_middleware allows - none of
        // which are under /admin - so every fetch below would just 403.
        // Sending the user to finish that first avoids a page full of
        // broken panels for a reason that has nothing to do with admin
        // access.
        if (me.must_change_password) {
          router.push("/account?forced=1");
          return;
        }
        if (!me.is_admin) {
          setDenyReason("You need administrator privileges to view this page.");
          setAllowed(false);
        } else {
          setAllowed(true);
        }
      } catch {
        setDenyReason("Could not reach the backend.");
        setAllowed(false);
      } finally {
        if (!cancelled) setChecking(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [router]);

  if (checking) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--background)] text-[var(--foreground)]">
        <p className="text-sm text-slate-500 dark:text-white/40">Loading…</p>
      </div>
    );
  }

  if (!allowed) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--background)] text-[var(--foreground)] p-6">
        <div className="max-w-md text-center space-y-4">
          <p className="text-red-500 text-sm bg-red-500/[0.08] p-4 rounded-xl border border-red-500/20">{denyReason}</p>
          <Link href="/dashboard" className="inline-flex items-center gap-1.5 text-sm text-cyan-500 hover:underline">
            <ArrowLeft className="w-4 h-4" /> Back to dashboard
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--background)] text-[var(--foreground)]">
      <header className="border-b border-slate-200 dark:border-white/[0.08] bg-white/90 dark:bg-black/80 backdrop-blur-xl sticky top-0 z-40">
        <div className="max-w-6xl mx-auto px-6 py-4 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <BrandLogo className="px-2.5 py-1.5" />
            <div>
              <h1 className="text-lg font-bold">Admin Console</h1>
              <Link href="/dashboard" className="inline-flex items-center gap-1.5 text-xs text-slate-500 dark:text-white/40 hover:text-cyan-500">
                <ArrowLeft className="w-3.5 h-3.5" /> Back to dashboard
              </Link>
            </div>
          </div>
          <nav className="flex items-center gap-1 flex-wrap">
            {TABS.map((tab) => {
              const active = tab.href === "/admin" ? pathname === "/admin" : pathname.startsWith(tab.href);
              const Icon = tab.icon;
              return (
                <Link
                  key={tab.href}
                  href={tab.href}
                  className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold transition-all ${
                    active
                      ? "bg-cyan-500/10 text-cyan-500 border border-cyan-500/25"
                      : "text-slate-500 dark:text-white/50 border border-transparent hover:bg-slate-100 dark:hover:bg-white/[0.05]"
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  {tab.label}
                </Link>
              );
            })}
          </nav>
          <NotificationBell />
        </div>
      </header>
      <main className="max-w-6xl mx-auto px-6 py-8">{children}</main>
    </div>
  );
}
