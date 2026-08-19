"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";
import { Eye, EyeOff, ArrowRight, Sparkles } from "lucide-react";
import BrandLogo from "@/components/BrandLogo";
import { BRAND_NAME, BRAND_TAGLINE } from "@/lib/brand";

/* ───────── floating particles (login version — fewer, subtler) ───────── */
function LoginParticles() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
      {Array.from({ length: 20 }).map((_, i) => {
        const size = 1 + (((i * 7) % 20) / 10);
        const left = (i * 19) % 100;
        const delay = (i * 3) % 6;
        const duration = 12 + ((i * 11) % 14);
        const opacity = 0.05 + (((i * 9) % 25) / 100);
        return (
          <motion.span
            key={i}
            className="absolute rounded-full"
            style={{
              width: size,
              height: size,
              left: `${left}%`,
              bottom: "-5%",
              background: i % 3 === 0 ? "#00f0ff" : i % 3 === 1 ? "#a855f7" : "#3b82f6",
              opacity,
            }}
            animate={{ y: [0, -1200], opacity: [opacity, 0] }}
            transition={{ duration, delay, repeat: Infinity, ease: "linear" }}
          />
        );
      })}
    </div>
  );
}

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });
  // Whether to offer "Request access". Deployments can disable self-service
  // registration, and a link to a form that always 403s is worse than no link.
  const [selfRegistration, setSelfRegistration] = useState(false);
  const [showDefaultPasswordPrompt, setShowDefaultPasswordPrompt] = useState(false);
  const [defaultPasswordMessage, setDefaultPasswordMessage] = useState(
    "You are using the default password for this account.",
  );
  const router = useRouter();

  useEffect(() => {
    const handler = (e: MouseEvent) => setMousePos({ x: e.clientX, y: e.clientY });
    window.addEventListener("mousemove", handler);
    return () => window.removeEventListener("mousemove", handler);
  }, []);

  useEffect(() => {
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/auth/registration-policy`)
      .then((r) => r.json())
      .then((d) => setSelfRegistration(Boolean(d.self_registration_enabled)))
      .catch(() => setSelfRegistration(false));
  }, []);

  const handleLogin = async (u: string, p: string) => {
    setError("");
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/auth/login?username=${encodeURIComponent(u)}&password=${encodeURIComponent(p)}`,
        { method: "POST" }
      );
      if (!res.ok) {
        // The backend distinguishes "wrong password" (401) from "your
        // account is pending approval / disabled" (403) and puts the
        // explanation in `detail`. Showing the raw body instead would print
        // a JSON blob at someone who just needs to know to wait for an admin.
        const data = await res.json().catch(() => null);
        throw new Error(data?.detail || "Invalid credentials");
      }
      const data = await res.json();
      localStorage.setItem("token", data.access_token);
      localStorage.setItem("role", data.role);
      // The workspace comes from the account; the server ignores anything the
      // client sends at login. Stored only so the UI can display it.
      localStorage.setItem("workspace_id", data.workspace_id || "default");
      localStorage.setItem("username", data.username || u);
      if (data.default_password_prompt) {
        setDefaultPasswordMessage(
          data.default_password_message ||
            "You are using the default password for this account.",
        );
        setShowDefaultPasswordPrompt(true);
        return;
      }
      if (data.must_change_password) {
        // The backend's credential_change_middleware refuses every other
        // route for this session until this happens - sending anywhere else
        // first would just bounce straight back with a 403.
        router.push("/account?forced=1");
        return;
      }
      router.push("/dashboard");
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Login failed";
      setError(message);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await handleLogin(username, password);
  };

  return (
    <div className="min-h-screen bg-[var(--background)] flex items-center justify-center p-6 text-[var(--foreground)] relative overflow-hidden">
      <LoginParticles />

      {/* mouse-tracking radial glow */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background: `radial-gradient(500px circle at ${mousePos.x}px ${mousePos.y}px, rgba(0,240,255,0.04), transparent 60%)`,
        }}
      />

      {/* static glow orbs */}
      <div className="absolute top-1/4 left-1/3 w-[400px] h-[400px] bg-cyan-500/[0.06] blur-[140px] rounded-full pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/3 w-[350px] h-[350px] bg-purple-600/[0.05] blur-[120px] rounded-full pointer-events-none" />

      <motion.div
        initial={{ opacity: 0, y: 20, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.6 }}
        className="relative w-full max-w-md z-10"
      >
        {/* card */}
        <div className="relative bg-white border border-slate-200 dark:bg-white/[0.03] dark:border-white/[0.08] backdrop-blur-2xl rounded-2xl p-8 md:p-10 shadow-[0_0_80px_rgba(0,240,255,0.04)] overflow-hidden">
          {/* corner glow accents */}
          <div className="absolute -top-24 -right-24 w-48 h-48 bg-cyan-500/[0.08] blur-[80px] rounded-full pointer-events-none" />
          <div className="absolute -bottom-24 -left-24 w-48 h-48 bg-purple-500/[0.06] blur-[80px] rounded-full pointer-events-none" />

          <div className="relative z-10">
            {/* logo + heading */}
            <div className="flex items-center gap-3 mb-8">
              <BrandLogo size={46} />
              <div>
                <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Welcome Back</h2>
                <p className="text-slate-500 dark:text-white/40 text-xs tracking-wide">Sign in to {BRAND_NAME}</p>
                <p className="mt-0.5 text-slate-400 dark:text-white/25 text-[11px] leading-snug">{BRAND_TAGLINE}</p>
              </div>
            </div>

            <form onSubmit={handleSubmit} className="space-y-5">
              {/* username */}
              <div>
                <label className="block text-xs font-semibold uppercase tracking-widest text-slate-500 dark:text-white/40 mb-2">Username</label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full bg-white border border-slate-300 dark:bg-black/60 dark:border-white/[0.08] rounded-xl px-4 py-3 text-slate-900 dark:text-white focus:outline-none focus:border-cyan-500/40 focus:ring-1 focus:ring-cyan-500/30 focus:shadow-[0_0_15px_rgba(0,240,255,0.08)] transition-all placeholder:text-slate-400 dark:placeholder:text-white/20"
                  placeholder="Enter your username"
                  required
                />
              </div>

              {/* password */}
              <div>
                <label className="block text-xs font-semibold uppercase tracking-widest text-slate-500 dark:text-white/40 mb-2">Password</label>
                <div className="relative">
                  <input
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full bg-white border border-slate-300 dark:bg-black/60 dark:border-white/[0.08] rounded-xl px-4 py-3 pr-12 text-slate-900 dark:text-white focus:outline-none focus:border-cyan-500/40 focus:ring-1 focus:ring-cyan-500/30 focus:shadow-[0_0_15px_rgba(0,240,255,0.08)] transition-all placeholder:text-slate-400 dark:placeholder:text-white/20"
                    placeholder="Enter your password"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 dark:text-white/25 hover:text-cyan-500 dark:hover:text-cyan-400 transition-colors"
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              {/* error */}
              {error && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  className="text-red-400 text-sm bg-red-500/[0.08] p-3 rounded-xl border border-red-500/20"
                >
                  {error}
                </motion.div>
              )}

              {/* submit */}
              <button
                type="submit"
                className="group relative w-full flex items-center justify-center gap-2 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-semibold py-3.5 rounded-xl transition-all shadow-[0_0_30px_rgba(0,240,255,0.2)] hover:shadow-[0_0_50px_rgba(0,240,255,0.35)] active:scale-[0.98]"
              >
                <span className="absolute inset-0 rounded-xl bg-gradient-to-r from-cyan-400 to-blue-500 opacity-0 group-hover:opacity-100 blur-xl transition-opacity" />
                <span className="relative">Sign In</span>
                <ArrowRight className="relative w-4 h-4 group-hover:translate-x-1 transition-transform" />
              </button>
            </form>

            {selfRegistration && (
              <p className="mt-6 text-center text-xs text-slate-500 dark:text-white/30">
                Need an account?{" "}
                <Link href="/register" className="text-cyan-500 hover:underline">
                  Request access
                </Link>
              </p>
            )}

            {/* subtle footer badge */}
            <div className="mt-8 flex items-center justify-center gap-1.5 text-[10px] text-slate-500 dark:text-white/20 uppercase tracking-widest">
              <Sparkles className="w-3 h-3" />
              Testrig Sentinel · QA Intelligence Platform
            </div>
          </div>
        </div>
      </motion.div>

      {showDefaultPasswordPrompt && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-6">
          <div
            className="absolute inset-0 bg-black/50 backdrop-blur-sm"
            onClick={() => setShowDefaultPasswordPrompt(false)}
          />
          <motion.div
            initial={{ opacity: 0, y: 12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            className="relative w-full max-w-md rounded-2xl border border-amber-500/30 bg-white dark:bg-slate-950 p-6 shadow-2xl"
          >
            <h3 className="text-lg font-bold text-slate-900 dark:text-white">Security Reminder</h3>
            <p className="mt-2 text-sm text-slate-600 dark:text-white/70">{defaultPasswordMessage}</p>
            <p className="mt-1 text-sm text-slate-600 dark:text-white/70">
              Choose an option:
            </p>
            <div className="mt-5 grid gap-3">
              <button
                type="button"
                onClick={() => {
                  setShowDefaultPasswordPrompt(false);
                  router.push("/account?default_password=1");
                }}
                className="w-full rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 px-4 py-3 text-sm font-semibold text-white"
              >
                Change Password
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowDefaultPasswordPrompt(false);
                  router.push("/dashboard");
                }}
                className="w-full rounded-xl border border-slate-300 dark:border-white/15 px-4 py-3 text-sm font-semibold text-slate-700 dark:text-white/80"
              >
                Remind Me Later
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </div>
  );
}
