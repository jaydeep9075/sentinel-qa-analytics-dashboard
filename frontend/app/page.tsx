"use client";
import Link from "next/link";
import { motion, useMotionValue, useSpring, useMotionTemplate } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import BrandLogo from "@/components/BrandLogo";
import {
  MessageSquare,
  BarChart3,
  Users,
  Zap,
  Shield,
  TrendingUp,
  ArrowRight,
  ChevronRight,
  Sparkles,
  Activity,
  Database,
  GitBranch,
  Star,
} from "lucide-react";

/* ───────── floating particles ───────── */
function Particles() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
      {/* Cool animated grid background */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#00f0ff15_1px,transparent_1px),linear-gradient(to_bottom,#00f0ff15_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_0%,#000_70%,transparent_100%)] opacity-40" />
      
      {/* Floating glowing orbs with slow-medium speed */}
      {Array.from({ length: 30 }).map((_, i) => {
        const size = 2 + ((i * 37) % 50) / 10;
        const left = (i * 17) % 100;
        const top = (i * 29) % 100;
        const delay = (i * 7) % 5;
        const duration = 12 + ((i * 11) % 10); // Slow-medium: 12 to 21 seconds
        const opacity = 0.2 + (((i * 13) % 50) / 100);
        const colors = ["#00f0ff", "#a855f7", "#3b82f6"];
        const color = colors[i % 3];
        
        // Deterministic directional drift for render-pure motion.
        const yDist = (30 + ((i * 19) % 40)) * (i % 2 === 0 ? -1 : 1);
        const xDist = (20 + ((i * 23) % 30)) * (i % 3 === 0 ? -1 : 1);
        
        return (
          <motion.span
            key={i}
            className="absolute rounded-full"
            style={{
              width: size,
              height: size,
              left: `${left}%`,
              top: `${top}%`,
              background: color,
              opacity,
              boxShadow: `0 0 ${size * 3}px ${color}`
            }}
            animate={{ 
              y: [0, yDist, 0], 
              x: [0, xDist, 0],
              scale: [1, 1.3, 1],
              opacity: [opacity, opacity * 1.5, opacity] 
            }}
            transition={{ duration, delay, repeat: Infinity, ease: "easeInOut" }}
          />
        );
      })}
    </div>
  );
}

/* ───────── neon line divider ───────── */
function NeonDivider() {
  return (
    <div className="relative h-px w-full max-w-5xl mx-auto my-4">
      <div className="absolute inset-0 bg-gradient-to-r from-transparent via-cyan-500/60 to-transparent" />
      <div className="absolute inset-0 bg-gradient-to-r from-transparent via-cyan-400/30 to-transparent blur-sm" />
    </div>
  );
}

/* ───────── main page ───────── */
export default function LandingPage() {
  const heroRef = useRef<HTMLDivElement>(null);
  const [launchHref, setLaunchHref] = useState("/login");
  
  // Smooth, lazy mouse follower using Framer Motion physics
  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);
  const smoothX = useSpring(mouseX, { stiffness: 20, damping: 25, mass: 1 });
  const smoothY = useSpring(mouseY, { stiffness: 20, damping: 25, mass: 1 });
  const backgroundTemplate = useMotionTemplate`radial-gradient(600px circle at ${smoothX}px ${smoothY}px, rgba(0,240,255,0.06), transparent 60%)`;

  useEffect(() => {
    // Center it initially to avoid snapping from top-left
    mouseX.set(window.innerWidth / 2);
    mouseY.set(window.innerHeight / 2);
    
    const handler = (e: MouseEvent) => {
      mouseX.set(e.clientX);
      mouseY.set(e.clientY);
    };
    window.addEventListener("mousemove", handler);
    return () => window.removeEventListener("mousemove", handler);
  }, [mouseX, mouseY]);

  useEffect(() => {
    if (localStorage.getItem("token")) {
      setLaunchHref("/dashboard");
    }
  }, []);

  return (
    <div className="min-h-screen bg-[var(--background)] text-[var(--foreground)] selection:bg-cyan-500/30 overflow-x-hidden">
      <Particles />

      {/* ══════════ NAVBAR ══════════ */}
      <motion.nav
        initial={{ y: -40, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.6 }}
        className="fixed top-0 inset-x-0 z-50 backdrop-blur-xl bg-white/80 border-b border-slate-200 dark:bg-black/60 dark:border-white/[0.06]"
      >
        <div className="max-w-7xl mx-auto flex items-center justify-between px-6 py-4">
          <div className="flex items-center gap-2">
            <BrandLogo className="shadow-[0_0_20px_rgba(0,240,255,0.2)]" />
            <span className="text-lg font-bold tracking-tight">
              <span className="text-cyan-400">Sentinel</span>{" "}
              <span className="text-slate-500 dark:text-white/70 font-normal">Analytics</span>
            </span>
          </div>
          <div className="hidden md:flex items-center gap-8 text-sm text-slate-500 dark:text-white/50">
            <a href="#features" className="hover:text-cyan-400 transition-colors">Features</a>
            <a href="#how-it-works" className="hover:text-cyan-400 transition-colors">How It Works</a>
            <a href="#tech" className="hover:text-cyan-400 transition-colors">Technology</a>
          </div>
          <Link
            href="/login"
            className="px-5 py-2 rounded-full text-sm font-medium border border-cyan-500/30 text-cyan-400 hover:bg-cyan-500/10 hover:border-cyan-400/50 hover:shadow-[0_0_20px_rgba(0,240,255,0.15)] transition-all"
          >
            Sign In
          </Link>
        </div>
      </motion.nav>

      {/* ══════════ HERO ══════════ */}
      <section ref={heroRef} className="relative pt-36 pb-28 lg:pt-52 lg:pb-40">
        {/* radial glow follows mouse */}
        <motion.div
          className="pointer-events-none absolute inset-0 transition-opacity duration-300"
          style={{
            background: backgroundTemplate,
          }}
        />
        {/* static glow orbs */}
        <div className="absolute top-20 left-1/4 w-[500px] h-[500px] bg-cyan-500/[0.09] blur-[140px] rounded-full pointer-events-none" />
        <div className="absolute bottom-0 right-1/4 w-[400px] h-[400px] bg-purple-600/[0.08] blur-[120px] rounded-full pointer-events-none" />

        <div className="relative max-w-5xl mx-auto px-6 text-center">
          <motion.div
            initial={{ opacity: 0, y: 24, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.7 }}
          >
            <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-cyan-50 border border-cyan-500/30 text-xs font-semibold uppercase tracking-widest text-cyan-600 dark:bg-white/[0.04] dark:text-cyan-400 mb-8 backdrop-blur-md shadow-[0_0_20px_rgba(0,240,255,0.15)]">
              <Sparkles className="w-3.5 h-3.5 animate-pulse" />
              AI-Powered QA Intelligence
            </div>
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.1 }}
            className="text-5xl md:text-7xl lg:text-8xl font-extrabold tracking-tight leading-[1.05] mb-8"
          >
            <span className="text-slate-900 dark:text-white">Decode Your</span>
            <br />
            <span className="bg-gradient-to-r from-cyan-400 via-blue-400 to-purple-500 bg-clip-text text-transparent drop-shadow-[0_0_40px_rgba(0,240,255,0.4)]">
              Software Quality
            </span>
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.2 }}
            className="text-base md:text-lg text-slate-600 dark:text-white/60 max-w-2xl mx-auto mb-12 leading-relaxed"
          >
            Ask questions in plain English. Get instant AI-driven insights, auto&#8209;generated charts, and executive&#8209;ready summaries from your test data.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.3 }}
            className="flex flex-col sm:flex-row items-center justify-center gap-4"
          >
            <Link
              href={launchHref}
              className="group relative inline-flex items-center gap-3 bg-gradient-to-r from-cyan-500 to-blue-600 text-white font-semibold px-8 py-4 rounded-full shadow-[0_0_40px_rgba(0,240,255,0.35)] hover:shadow-[0_0_60px_rgba(0,240,255,0.5)] hover:-translate-y-0.5 transition-all"
            >
              <span className="absolute inset-0 rounded-full bg-gradient-to-r from-cyan-400 to-blue-500 opacity-0 group-hover:opacity-100 blur-xl transition-opacity" />
              <span className="relative">Launch Dashboard</span>
              <ArrowRight className="relative w-5 h-5 group-hover:translate-x-1 transition-transform" />
            </Link>
            <a
              href="#features"
              className="inline-flex items-center gap-2 px-6 py-4 rounded-full border border-slate-300 text-slate-600 hover:text-slate-900 hover:border-slate-400 hover:bg-slate-100 dark:border-white/10 dark:text-white/60 dark:hover:text-white dark:hover:border-white/20 dark:hover:bg-white/[0.03] transition-all text-sm font-medium"
            >
              Explore Features <ChevronRight className="w-4 h-4" />
            </a>
          </motion.div>
        </div>
      </section>

      <NeonDivider />

      {/* ══════════ FEATURES ══════════ */}
      <section id="features" className="py-24 relative">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[600px] bg-purple-600/[0.04] blur-[160px] rounded-full pointer-events-none" />

        <div className="max-w-6xl mx-auto px-6 relative">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="text-center mb-16"
          >
            <span className="text-xs font-semibold uppercase tracking-widest text-cyan-500 mb-3 block">Capabilities</span>
            <h2 className="text-3xl md:text-5xl font-bold mb-4">
              Everything You Need,{" "}
              <span className="bg-gradient-to-r from-cyan-400 to-purple-400 bg-clip-text text-transparent">Nothing You Don&apos;t</span>
            </h2>
            <p className="text-slate-600 dark:text-white/40 max-w-xl mx-auto">Powerful analytics wrapped in simplicity. Built for teams that ship fast and need clarity.</p>
          </motion.div>

          <div className="grid md:grid-cols-3 gap-6">
            {features.map((f, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, delay: i * 0.08 }}
                className="group relative p-8 rounded-2xl border border-slate-200 bg-white backdrop-blur-sm dark:border-white/[0.05] dark:bg-white/[0.02] hover:border-cyan-500/30 dark:hover:bg-white/[0.04] transition-all overflow-hidden shadow-lg hover:shadow-[0_0_30px_rgba(0,240,255,0.1)]"
              >
                {/* hover glow */}
                <div className="absolute -top-20 -right-20 w-40 h-40 bg-cyan-500/[0.08] blur-3xl rounded-full opacity-0 group-hover:opacity-100 transition-opacity" />
                <div className={`relative w-12 h-12 rounded-xl flex items-center justify-center mb-6 border border-slate-200 dark:border-white/[0.06] ${f.iconBg}`}>
                  {f.icon}
                </div>
                <h3 className="text-lg font-semibold mb-2 text-slate-900 dark:text-white">{f.title}</h3>
                <p className="text-slate-600 dark:text-white/40 text-sm leading-relaxed">{f.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      <NeonDivider />

      {/* ══════════ HOW IT WORKS ══════════ */}
      <section id="how-it-works" className="py-24 relative">
        <div className="max-w-5xl mx-auto px-6">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="text-center mb-16"
          >
            <span className="text-xs font-semibold uppercase tracking-widest text-cyan-500 mb-3 block">Workflow</span>
            <h2 className="text-3xl md:text-5xl font-bold mb-4">Three Steps to <span className="bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">Clarity</span></h2>
            <p className="text-slate-600 dark:text-white/40 max-w-xl mx-auto">From raw test data to boardroom-ready insights in under a minute.</p>
          </motion.div>

          <div className="grid md:grid-cols-3 gap-10 relative">
            {/* connector line */}
            <div className="hidden md:block absolute top-16 left-[18%] right-[18%] h-px bg-gradient-to-r from-cyan-500/0 via-cyan-500/50 to-cyan-500/0" />
            <div className="hidden md:block absolute top-16 left-[18%] right-[18%] h-px bg-gradient-to-r from-cyan-500/0 via-cyan-500/30 to-cyan-500/0 blur-sm" />

            {steps.map((step, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, delay: i * 0.15 }}
                className="relative text-center z-10"
              >
                <div className="w-[72px] h-[72px] mx-auto rounded-full bg-white border border-cyan-500/30 dark:bg-black flex items-center justify-center text-2xl font-bold mb-6 shadow-[0_0_30px_rgba(0,240,255,0.2)]">
                  <span className="bg-gradient-to-b from-cyan-400 to-blue-600 bg-clip-text text-transparent">{step.num}</span>
                </div>
                <h3 className="text-xl font-bold mb-3 text-slate-900 dark:text-white">{step.title}</h3>
                <p className="text-slate-600 dark:text-white/40 text-sm leading-relaxed px-2">{step.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      <NeonDivider />

      {/* ══════════ TECH STACK ══════════ */}
      <section id="tech" className="py-24 relative">
        <div className="max-w-5xl mx-auto px-6">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="text-center mb-16"
          >
            <span className="text-xs font-semibold uppercase tracking-widest text-cyan-500 mb-3 block">Under the Hood</span>
            <h2 className="text-3xl md:text-5xl font-bold mb-4">
              Built With{" "}
              <span className="bg-gradient-to-r from-cyan-400 to-purple-400 bg-clip-text text-transparent">Modern Tech</span>
            </h2>
          </motion.div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-5">
            {techStack.map((t, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, scale: 0.9 }}
                whileInView={{ opacity: 1, scale: 1 }}
                viewport={{ once: true }}
                transition={{ duration: 0.4, delay: i * 0.05 }}
                className="group flex flex-col items-center gap-3 p-6 rounded-2xl border border-slate-200 bg-white dark:border-white/[0.05] dark:bg-white/[0.02] hover:border-cyan-500/30 dark:hover:bg-white/[0.04] hover:shadow-[0_0_20px_rgba(0,240,255,0.1)] transition-all"
              >
                <div className="text-2xl group-hover:scale-110 group-hover:drop-shadow-[0_0_15px_currentColor] transition-all">{t.icon}</div>
                <span className="text-sm font-medium text-slate-600 dark:text-white/60 group-hover:text-cyan-500 dark:group-hover:text-cyan-400 transition-colors">{t.name}</span>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      <NeonDivider />

      {/* ══════════ CTA ══════════ */}
      <section className="py-28 relative">
        <div className="absolute inset-0 bg-gradient-to-t from-cyan-500/[0.05] to-transparent pointer-events-none" />
        <div className="max-w-3xl mx-auto px-6 text-center relative">
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
          >
            <h2 className="text-3xl md:text-5xl font-bold mb-6">
              Ready to <span className="bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent drop-shadow-[0_0_20px_rgba(0,240,255,0.3)]">Transform</span> Your QA?
            </h2>
            <p className="text-slate-600 dark:text-white/40 mb-10 max-w-lg mx-auto">Stop drowning in spreadsheets. Start making decisions backed by AI-powered insights.</p>
            <Link
              href={launchHref}
              className="group relative inline-flex items-center gap-3 bg-gradient-to-r from-cyan-500 to-blue-600 text-white font-semibold px-10 py-4 rounded-full shadow-[0_0_50px_rgba(0,240,255,0.35)] hover:shadow-[0_0_70px_rgba(0,240,255,0.5)] hover:-translate-y-0.5 transition-all"
            >
              <span className="absolute inset-0 rounded-full bg-gradient-to-r from-cyan-400 to-blue-500 opacity-0 group-hover:opacity-100 blur-xl transition-opacity" />
              <span className="relative">Get Started</span>
              <ArrowRight className="relative w-5 h-5 group-hover:translate-x-1 transition-transform" />
            </Link>
          </motion.div>
        </div>
      </section>

      {/* ══════════ FOOTER ══════════ */}
      <footer className="border-t border-slate-200 dark:border-white/[0.05] py-12 relative z-10">
        <div className="max-w-6xl mx-auto px-6 flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-md bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center shadow-[0_0_12px_rgba(0,240,255,0.2)]">
              <Shield className="w-4 h-4 text-white" />
            </div>
            <span className="text-sm font-semibold text-slate-600 dark:text-white/60">Sentinel Analytics</span>
          </div>
          <div className="flex items-center gap-6 text-xs text-slate-600 dark:text-white/40">
            <span>© {new Date().getFullYear()} Sentinel - testrig technologies pvt.ltd. All rights reserved.</span>
            <a href="#" className="hover:text-cyan-400 transition-colors">Privacy</a>
            <a href="#" className="hover:text-cyan-400 transition-colors">Terms</a>
          </div>
        </div>
      </footer>
    </div>
  );
}

/* ──────────── DATA ──────────── */
const features = [
  {
    icon: <MessageSquare className="w-5 h-5 text-cyan-400" />,
    iconBg: "bg-cyan-500/[0.08]",
    title: "Natural Language Queries",
    desc: "Ask 'How many tests failed today?' or 'Is the payment module stable?' — get instant, clear answers.",
  },
  {
    icon: <BarChart3 className="w-5 h-5 text-purple-400" />,
    iconBg: "bg-purple-500/[0.08]",
    title: "Auto-Generated Charts",
    desc: "Beautiful, presentation-ready visualizations created on-the-fly from a single conversational prompt.",
  },
  {
    icon: <Users className="w-5 h-5 text-blue-400" />,
    iconBg: "bg-blue-500/[0.08]",
    title: "Role-Based Insights",
    desc: "CTO gets executive summaries & ROI metrics. QA Engineers get deep technical breakdowns. One platform.",
  },
  {
    icon: <Zap className="w-5 h-5 text-amber-400" />,
    iconBg: "bg-amber-500/[0.08]",
    title: "Real-Time Analysis",
    desc: "Instantly process thousands of test results and surface the patterns that matter most to your team.",
  },
  {
    icon: <TrendingUp className="w-5 h-5 text-emerald-400" />,
    iconBg: "bg-emerald-500/[0.08]",
    title: "Build Trend Tracking",
    desc: "Compare pass rates, durations, and regressions across builds with interactive trend visualizations.",
  },
  {
    icon: <Shield className="w-5 h-5 text-rose-400" />,
    iconBg: "bg-rose-500/[0.08]",
    title: "Go/No-Go Decisions",
    desc: "AI-powered release readiness verdicts backed by data — so you can ship with confidence every time.",
  },
];

const steps = [
  { num: "01", title: "Upload Your Data", desc: "Import test results from Allure reports, JUnit XMLs, CSVs, or connect your CI/CD pipeline directly." },
  { num: "02", title: "Ask Anything", desc: "Type natural questions like 'Show me the top 10 slowest tests' or 'Which module has the most flaky tests?'" },
  { num: "03", title: "Get Visual Answers", desc: "Receive AI summaries, interactive charts, and actionable recommendations — ready for any stakeholder." },
];

const techStack = [
  { icon: <Activity className="w-6 h-6 text-cyan-400" />, name: "Next.js" },
  { icon: <Zap className="w-6 h-6 text-amber-400" />, name: "FastAPI" },
  { icon: <Sparkles className="w-6 h-6 text-purple-400" />, name: "Gemini AI" },
  { icon: <Database className="w-6 h-6 text-emerald-400" />, name: "SQLite" },
  { icon: <BarChart3 className="w-6 h-6 text-blue-400" />, name: "Recharts" },
  { icon: <GitBranch className="w-6 h-6 text-rose-400" />, name: "CI/CD Ready" },
  { icon: <Shield className="w-6 h-6 text-indigo-400" />, name: "Secure Auth" },
  { icon: <Star className="w-6 h-6 text-yellow-400" />, name: "Framer Motion" },
];
