"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Shield, Eye, EyeOff, ArrowRight, Sparkles } from "lucide-react";

/* ───────── floating particles (login version — fewer, subtler) ───────── */
function LoginParticles() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
      {Array.from({ length: 20 }).map((_, i) => {
        const size = Math.random() * 2 + 1;
        const left = Math.random() * 100;
        const delay = Math.random() * 6;
        const duration = Math.random() * 14 + 12;
        const opacity = Math.random() * 0.25 + 0.05;
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
  const router = useRouter();

  useEffect(() => {
    const handler = (e: MouseEvent) => setMousePos({ x: e.clientX, y: e.clientY });
    window.addEventListener("mousemove", handler);
    return () => window.removeEventListener("mousemove", handler);
  }, []);

  const handleLogin = async (u: string, p: string) => {
    setError("");
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/auth/login?username=${encodeURIComponent(u)}&password=${encodeURIComponent(p)}`,
        { method: "POST" }
      );
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || "Invalid credentials");
      }
      const data = await res.json();
      localStorage.setItem("token", data.access_token);
      localStorage.setItem("role", data.role);
      localStorage.setItem("username", u);
      router.push("/dashboard");
    } catch (err: any) {
      setError(err.message || "Login failed");
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await handleLogin(username, password);
  };

  return (
    <div className="min-h-screen bg-black flex items-center justify-center p-6 text-white relative overflow-hidden">
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
        <div className="relative bg-white/[0.03] backdrop-blur-2xl rounded-2xl p-8 md:p-10 border border-white/[0.08] shadow-[0_0_80px_rgba(0,240,255,0.04)] overflow-hidden">
          {/* corner glow accents */}
          <div className="absolute -top-24 -right-24 w-48 h-48 bg-cyan-500/[0.08] blur-[80px] rounded-full pointer-events-none" />
          <div className="absolute -bottom-24 -left-24 w-48 h-48 bg-purple-500/[0.06] blur-[80px] rounded-full pointer-events-none" />

          <div className="relative z-10">
            {/* logo + heading */}
            <div className="flex items-center gap-3 mb-8">
              <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center shadow-[0_0_24px_rgba(0,240,255,0.25)]">
                <Shield className="w-6 h-6 text-white" />
              </div>
              <div>
                <h2 className="text-2xl font-bold text-white">Welcome Back</h2>
                <p className="text-white/30 text-xs tracking-wide">Sign in to Sentinel Analytics</p>
              </div>
            </div>

            <form onSubmit={handleSubmit} className="space-y-5">
              {/* username */}
              <div>
                <label className="block text-xs font-semibold uppercase tracking-widest text-white/40 mb-2">Username</label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full bg-black/60 border border-white/[0.08] rounded-xl px-4 py-3 text-white focus:outline-none focus:border-cyan-500/40 focus:ring-1 focus:ring-cyan-500/30 focus:shadow-[0_0_15px_rgba(0,240,255,0.08)] transition-all placeholder:text-white/20"
                  placeholder="Enter your username"
                  required
                />
              </div>

              {/* password */}
              <div>
                <label className="block text-xs font-semibold uppercase tracking-widest text-white/40 mb-2">Password</label>
                <div className="relative">
                  <input
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full bg-black/60 border border-white/[0.08] rounded-xl px-4 py-3 pr-12 text-white focus:outline-none focus:border-cyan-500/40 focus:ring-1 focus:ring-cyan-500/30 focus:shadow-[0_0_15px_rgba(0,240,255,0.08)] transition-all placeholder:text-white/20"
                    placeholder="Enter your password"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-white/25 hover:text-cyan-400 transition-colors"
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

            {/* subtle footer badge */}
            <div className="mt-8 flex items-center justify-center gap-1.5 text-[10px] text-white/20 uppercase tracking-widest">
              <Sparkles className="w-3 h-3" />
              Sentinel QA Intelligence Platform
            </div>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
