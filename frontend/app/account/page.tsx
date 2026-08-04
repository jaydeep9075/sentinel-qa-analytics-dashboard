"use client";
import { useEffect, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";
import { AlertTriangle, ArrowLeft, Eye, EyeOff, KeyRound, ShieldCheck, UserCog } from "lucide-react";
import BrandLogo from "@/components/BrandLogo";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function authHeaders(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function AccountPageInner() {
  const router = useRouter();
  const params = useSearchParams();
  // Set only when redirected here because the account's session cannot reach
  // any other route yet (see services/main.py credential_change_middleware).
  // Not a security boundary by itself - the backend enforces the lock
  // regardless of what this page shows - just what makes the reason visible
  // instead of the user landing on a bare form with no context.
  const forced = params.get("forced") === "1";

  const [username, setUsername] = useState("");
  const [showPasswordForm, setShowPasswordForm] = useState(true);
  const [showUsernameForm, setShowUsernameForm] = useState(false);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [passwordError, setPasswordError] = useState("");
  const [passwordNotice, setPasswordNotice] = useState("");
  const [passwordBusy, setPasswordBusy] = useState(false);

  const [usernamePassword, setUsernamePassword] = useState("");
  const [newUsername, setNewUsername] = useState("");
  const [usernameError, setUsernameError] = useState("");
  const [usernameNotice, setUsernameNotice] = useState("");
  const [usernameBusy, setUsernameBusy] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem("username") || "";
    setUsername(stored);
    setNewUsername(stored);
    if (!localStorage.getItem("token")) {
      router.push("/login");
    }
  }, [router]);

  const submitPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordError("");
    setPasswordNotice("");
    if (newPassword !== confirmPassword) {
      setPasswordError("New password and confirmation do not match.");
      return;
    }
    setPasswordBusy(true);
    try {
      const res = await fetch(`${API}/auth/account/password`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Could not change password");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      if (forced) {
        // The gate is lifted the moment this call succeeds - the session no
        // longer needs a username change to proceed, so continue straight
        // into the app rather than making the change-username form
        // mandatory too.
        router.push("/dashboard");
        return;
      }
      setPasswordNotice("Password updated.");
    } catch (err: unknown) {
      setPasswordError(err instanceof Error ? err.message : "Could not change password");
    } finally {
      setPasswordBusy(false);
    }
  };

  const submitUsername = async (e: React.FormEvent) => {
    e.preventDefault();
    setUsernameError("");
    setUsernameNotice("");
    setUsernameBusy(true);
    try {
      const res = await fetch(`${API}/auth/account/username`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ current_password: usernamePassword, new_username: newUsername }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Could not change username");
      // A rename re-issues the token under the new name (see the backend
      // route's docstring) - the old token would 401 on the very next
      // request otherwise, since get_current_user trusts the JWT's `sub`
      // without re-checking the store.
      localStorage.setItem("token", data.access_token);
      localStorage.setItem("username", data.username);
      localStorage.setItem("role", data.role);
      setUsername(data.username);
      setUsernamePassword("");
      setUsernameNotice(`Username changed to "${data.username}".`);
    } catch (err: unknown) {
      setUsernameError(err instanceof Error ? err.message : "Could not change username");
    } finally {
      setUsernameBusy(false);
    }
  };

  const inputCls =
    "w-full rounded-xl border border-slate-300 dark:border-white/[0.08] bg-white dark:bg-black/60 px-4 py-2.5 text-sm text-slate-900 dark:text-white focus:outline-none focus:border-cyan-500/40 focus:ring-1 focus:ring-cyan-500/30 placeholder:text-slate-400 dark:placeholder:text-white/20";

  return (
    <div className="min-h-screen bg-[var(--background)] text-[var(--foreground)] p-6 md:p-10">
      <div className="max-w-2xl mx-auto space-y-6">
        <div className="flex items-center gap-3">
          <BrandLogo className="px-2.5 py-1.5" />
          <div>
            <h1 className="text-xl font-bold">Account settings</h1>
            {!forced && (
              <Link href="/dashboard" className="inline-flex items-center gap-1.5 text-xs text-slate-500 dark:text-white/40 hover:text-cyan-500">
                <ArrowLeft className="w-3.5 h-3.5" /> Back to dashboard
              </Link>
            )}
          </div>
        </div>

        {forced && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex items-start gap-3 rounded-xl border border-amber-500/30 bg-amber-500/[0.08] p-4"
          >
            <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
            <div className="text-sm">
              <p className="font-semibold text-amber-600 dark:text-amber-400">
                You&apos;re signed in with a temporary password.
              </p>
              <p className="text-amber-700/80 dark:text-amber-300/70 mt-1">
                Set a new password to continue — every other page is locked until you do.
                You can change your username here too, but it isn&apos;t required.
              </p>
            </div>
          </motion.div>
        )}

        <div className="rounded-xl border border-slate-200 dark:border-white/[0.08] bg-white dark:bg-white/[0.02] p-4 flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-cyan-500/10 flex items-center justify-center text-cyan-500 font-bold uppercase">
            {username ? username[0] : "?"}
          </div>
          <div>
            <p className="text-sm font-semibold">{username || "…"}</p>
            <p className="text-xs text-slate-500 dark:text-white/40">Signed in</p>
          </div>
        </div>

        {/* Password */}
        <section className="rounded-xl border border-slate-200 dark:border-white/[0.08] overflow-hidden">
          <button
            type="button"
            onClick={() => setShowPasswordForm((v) => !v)}
            className="w-full flex items-center gap-2 px-5 py-4 text-left bg-slate-50 dark:bg-white/[0.02]"
          >
            <KeyRound className="w-4 h-4 text-cyan-500" />
            <span className="text-sm font-semibold flex-1">Change password</span>
            {forced && <span className="text-[10px] uppercase tracking-widest text-amber-500 font-bold">Required</span>}
          </button>
          {showPasswordForm && (
            <form onSubmit={submitPassword} className="p-5 space-y-4">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-widest text-slate-500 dark:text-white/40 mb-1.5">
                  Current password
                </label>
                <input
                  type="password"
                  required
                  className={inputCls}
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase tracking-widest text-slate-500 dark:text-white/40 mb-1.5">
                  New password
                </label>
                <div className="relative">
                  <input
                    type={showPw ? "text" : "password"}
                    required
                    minLength={8}
                    className={`${inputCls} pr-11`}
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPw((v) => !v)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 dark:text-white/25 hover:text-cyan-500"
                  >
                    {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
                <p className="mt-1 text-[11px] text-slate-400 dark:text-white/30">At least 8 characters.</p>
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase tracking-widest text-slate-500 dark:text-white/40 mb-1.5">
                  Confirm new password
                </label>
                <input
                  type={showPw ? "text" : "password"}
                  required
                  className={inputCls}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                />
              </div>
              {passwordError && (
                <div className="text-red-500 text-sm bg-red-500/[0.08] p-3 rounded-xl border border-red-500/20">{passwordError}</div>
              )}
              {passwordNotice && (
                <div className="text-emerald-500 text-sm bg-emerald-500/[0.08] p-3 rounded-xl border border-emerald-500/20">{passwordNotice}</div>
              )}
              <button
                type="submit"
                disabled={passwordBusy}
                className="w-full py-3 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 text-white font-semibold text-sm disabled:opacity-60"
              >
                {passwordBusy ? "Updating…" : "Update password"}
              </button>
            </form>
          )}
        </section>

        {/* Username */}
        <section className="rounded-xl border border-slate-200 dark:border-white/[0.08] overflow-hidden">
          <button
            type="button"
            onClick={() => setShowUsernameForm((v) => !v)}
            className="w-full flex items-center gap-2 px-5 py-4 text-left bg-slate-50 dark:bg-white/[0.02]"
          >
            <UserCog className="w-4 h-4 text-purple-500" />
            <span className="text-sm font-semibold flex-1">Change username</span>
            <span className="text-[10px] uppercase tracking-widest text-slate-400 dark:text-white/30">Optional</span>
          </button>
          {showUsernameForm && (
            <form onSubmit={submitUsername} className="p-5 space-y-4">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-widest text-slate-500 dark:text-white/40 mb-1.5">
                  New username
                </label>
                <input
                  type="text"
                  required
                  minLength={3}
                  maxLength={64}
                  pattern="[A-Za-z0-9._\-]+"
                  title="Letters, numbers, dot, underscore and hyphen only"
                  className={inputCls}
                  value={newUsername}
                  onChange={(e) => setNewUsername(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase tracking-widest text-slate-500 dark:text-white/40 mb-1.5">
                  Current password (to confirm)
                </label>
                <input
                  type="password"
                  required
                  className={inputCls}
                  value={usernamePassword}
                  onChange={(e) => setUsernamePassword(e.target.value)}
                />
              </div>
              {usernameError && (
                <div className="text-red-500 text-sm bg-red-500/[0.08] p-3 rounded-xl border border-red-500/20">{usernameError}</div>
              )}
              {usernameNotice && (
                <div className="text-emerald-500 text-sm bg-emerald-500/[0.08] p-3 rounded-xl border border-emerald-500/20">{usernameNotice}</div>
              )}
              <button
                type="submit"
                disabled={usernameBusy}
                className="w-full py-3 rounded-xl border border-purple-500/30 text-purple-600 dark:text-purple-400 font-semibold text-sm disabled:opacity-60 hover:bg-purple-500/[0.06]"
              >
                {usernameBusy ? "Updating…" : "Update username"}
              </button>
            </form>
          )}
        </section>

        <div className="flex items-center gap-2 text-[11px] text-slate-400 dark:text-white/30 justify-center">
          <ShieldCheck className="w-3.5 h-3.5" />
          Changes take effect immediately for this session.
        </div>
      </div>
    </div>
  );
}

export default function AccountPage() {
  return (
    <Suspense fallback={null}>
      <AccountPageInner />
    </Suspense>
  );
}
