"use client";
import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Gauge, KeyRound, ScrollText, Settings as SettingsIcon, Users } from "lucide-react";
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
        </div>
      </header>
      <main className="max-w-6xl mx-auto px-6 py-8">{children}</main>
    </div>
  );
}
