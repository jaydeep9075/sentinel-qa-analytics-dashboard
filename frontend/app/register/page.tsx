"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { Eye, EyeOff, ArrowRight, CheckCircle2, Clock } from "lucide-react";
import BrandLogo from "@/components/BrandLogo";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Outcome = { status: "pending" | "active"; message: string };

export default function RegisterPage() {
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [workspace, setWorkspace] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  // Registration can be switched off per deployment. Ask the backend rather
  // than assuming, so a locked-down install doesn't show a form that will
  // only ever return 403.
  const [enabled, setEnabled] = useState<boolean | null>(null);

  useEffect(() => {
    fetch(`${API}/auth/registration-policy`)
      .then((r) => r.json())
      .then((d) => setEnabled(Boolean(d.self_registration_enabled)))
      .catch(() => setEnabled(true));
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }

    setBusy(true);
    try {
      const res = await fetch(`${API}/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username,
          password,
          email: email || null,
          requested_workspace: workspace || null,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Registration failed");
      setOutcome({ status: data.status, message: data.message });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setBusy(false);
    }
  };

  const field =
    "w-full bg-white border border-slate-300 dark:bg-black/60 dark:border-white/[0.08] rounded-xl px-4 py-3 text-slate-900 dark:text-white focus:outline-none focus:border-cyan-500/40 focus:ring-1 focus:ring-cyan-500/30 transition-all placeholder:text-slate-400 dark:placeholder:text-white/20";
  const label =
    "block text-xs font-semibold uppercase tracking-widest text-slate-500 dark:text-white/40 mb-2";

  return (
    <div className="min-h-screen bg-[var(--background)] flex items-center justify-center p-6 text-[var(--foreground)]">
      <div className="absolute top-1/4 left-1/3 w-[400px] h-[400px] bg-cyan-500/[0.06] blur-[140px] rounded-full pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/3 w-[350px] h-[350px] bg-purple-600/[0.05] blur-[120px] rounded-full pointer-events-none" />

      <motion.div
        initial={{ opacity: 0, y: 20, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.5 }}
        className="relative w-full max-w-md z-10"
      >
        <div className="relative bg-white border border-slate-200 dark:bg-white/[0.03] dark:border-white/[0.08] backdrop-blur-2xl rounded-2xl p-8 md:p-10 shadow-[0_0_80px_rgba(0,240,255,0.04)]">
          <div className="flex items-center gap-3 mb-8">
            <BrandLogo className="px-3 py-2 shadow-[0_0_24px_rgba(0,240,255,0.18)]" />
            <div>
              <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Request Access</h2>
              <p className="text-slate-500 dark:text-white/30 text-xs tracking-wide">
                Create a Sentinel Analytics account
              </p>
            </div>
          </div>

          {enabled === false && (
            <div className="text-sm text-slate-600 dark:text-white/50 space-y-4">
              <p>
                Self-service registration is turned off on this deployment. Ask an administrator to
                create an account for you.
              </p>
              <Link href="/login" className="text-cyan-500 hover:underline inline-block">
                Back to sign in
              </Link>
            </div>
          )}

          {outcome && (
            <div className="space-y-5">
              <div
                className={`flex gap-3 p-4 rounded-xl border ${
                  outcome.status === "active"
                    ? "bg-emerald-500/[0.08] border-emerald-500/25 text-emerald-600 dark:text-emerald-400"
                    : "bg-amber-500/[0.08] border-amber-500/25 text-amber-600 dark:text-amber-400"
                }`}
              >
                {outcome.status === "active" ? (
                  <CheckCircle2 className="w-5 h-5 shrink-0 mt-0.5" />
                ) : (
                  <Clock className="w-5 h-5 shrink-0 mt-0.5" />
                )}
                <div className="text-sm">
                  <p className="font-semibold mb-1">
                    {outcome.status === "active" ? "Account ready" : "Awaiting approval"}
                  </p>
                  <p className="opacity-90">{outcome.message}</p>
                </div>
              </div>
              <Link
                href="/login"
                className="w-full flex items-center justify-center gap-2 bg-gradient-to-r from-cyan-500 to-blue-600 text-white font-semibold py-3.5 rounded-xl"
              >
                Go to sign in <ArrowRight className="w-4 h-4" />
              </Link>
            </div>
          )}

          {enabled !== false && !outcome && (
            <form onSubmit={submit} className="space-y-4">
              <div>
                <label className={label}>Username</label>
                <input
                  className={field}
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="jane.doe"
                  minLength={3}
                  required
                />
              </div>

              <div>
                <label className={label}>Email</label>
                <input
                  className={field}
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="jane@company.com"
                />
              </div>

              <div>
                <label className={label}>Team / workspace</label>
                <input
                  className={field}
                  value={workspace}
                  onChange={(e) => setWorkspace(e.target.value)}
                  placeholder="platform"
                />
                <p className="text-[11px] text-slate-400 dark:text-white/25 mt-1.5">
                  A request, not a grant — an administrator confirms which workspace you join.
                </p>
              </div>

              <div>
                <label className={label}>Password</label>
                <div className="relative">
                  <input
                    className={`${field} pr-12`}
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="At least 8 characters"
                    minLength={8}
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 dark:text-white/25 hover:text-cyan-500"
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              <div>
                <label className={label}>Confirm password</label>
                <input
                  className={field}
                  type={showPassword ? "text" : "password"}
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  required
                />
              </div>

              {error && (
                <div className="text-red-400 text-sm bg-red-500/[0.08] p-3 rounded-xl border border-red-500/20">
                  {error}
                </div>
              )}

              <button
                type="submit"
                disabled={busy}
                className="group w-full flex items-center justify-center gap-2 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 disabled:opacity-50 text-white font-semibold py-3.5 rounded-xl transition-all shadow-[0_0_30px_rgba(0,240,255,0.2)] active:scale-[0.98]"
              >
                {busy ? "Submitting…" : "Request access"}
                {!busy && <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />}
              </button>

              <p className="text-center text-xs text-slate-500 dark:text-white/30 pt-2">
                Already have an account?{" "}
                <Link href="/login" className="text-cyan-500 hover:underline">
                  Sign in
                </Link>
              </p>
            </form>
          )}
        </div>
      </motion.div>
    </div>
  );
}
