"use client";
import Link from "next/link";
import {
  motion,
  useMotionValue,
  useSpring,
  useMotionTemplate,
  useReducedMotion,
} from "framer-motion";
import { useEffect, useState } from "react";
import BrandLogo from "@/components/BrandLogo";
import TestrigWordmark from "@/components/TestrigWordmark";
import { BRAND_TAGLINE } from "@/lib/brand";
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
  Database,
  Globe,
  FileArchive,
  FileSpreadsheet,
  Radio,
  Check,
  X,
  Search,
  Send,
  Clock,
  Wallet,
  Target,
  Rocket,
  Briefcase,
  Lock,
} from "lucide-react";

/* ═══════════════════════════════════════════════════════════
   Ambient background
   ═══════════════════════════════════════════════════════════ */

function Ambience() {
  const reduce = useReducedMotion();

  return (
    <div className="pointer-events-none fixed inset-0 overflow-hidden" aria-hidden>
      {/* grid, faded out toward the bottom of the viewport */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#00f0ff12_1px,transparent_1px),linear-gradient(to_bottom,#00f0ff12_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_70%_60%_at_50%_0%,#000_60%,transparent_100%)] opacity-50" />

      {/* Drifting motes. Deliberately few: this layer sits behind every
          section of a long page, so each extra element is a permanent
          compositor cost for a decorative effect. Skipped outright when the
          visitor has asked for reduced motion. */}
      {!reduce &&
        Array.from({ length: 16 }).map((_, i) => {
          const size = 2 + ((i * 37) % 40) / 10;
          const left = (i * 23) % 100;
          const top = (i * 31) % 100;
          const color = ["#00f0ff", "#a855f7", "#3b82f6"][i % 3];
          const opacity = 0.15 + ((i * 13) % 35) / 100;

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
                boxShadow: `0 0 ${size * 3}px ${color}`,
              }}
              animate={{
                y: [0, (30 + ((i * 19) % 40)) * (i % 2 === 0 ? -1 : 1), 0],
                x: [0, (20 + ((i * 29) % 30)) * (i % 3 === 0 ? -1 : 1), 0],
                opacity: [opacity, opacity * 1.6, opacity],
              }}
              transition={{
                duration: 14 + ((i * 11) % 10),
                delay: (i * 7) % 5,
                repeat: Infinity,
                ease: "easeInOut",
              }}
            />
          );
        })}
    </div>
  );
}

function NeonDivider() {
  return (
    <div className="relative mx-auto my-4 h-px w-full max-w-5xl">
      <div className="absolute inset-0 bg-gradient-to-r from-transparent via-cyan-500/60 to-transparent" />
      <div className="absolute inset-0 bg-gradient-to-r from-transparent via-cyan-400/30 to-transparent blur-sm" />
    </div>
  );
}

function SectionHeading({
  eyebrow,
  title,
  accent,
  sub,
}: {
  /** Optional — sections that read fine without a kicker just omit it. */
  eyebrow?: string;
  title: string;
  accent?: string;
  sub?: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-80px" }}
      transition={{ duration: 0.5 }}
      className="mb-14 text-center"
    >
      {eyebrow && (
        <span className="mb-3 block text-xs font-semibold uppercase tracking-widest text-cyan-500">
          {eyebrow}
        </span>
      )}
      <h2 className="mb-4 text-3xl font-bold md:text-5xl">
        {title}{" "}
        {accent && (
          <span className="bg-gradient-to-r from-cyan-400 to-purple-400 bg-clip-text text-transparent">
            {accent}
          </span>
        )}
      </h2>
      {sub && (
        <p className="mx-auto max-w-2xl text-slate-600 dark:text-white/45">{sub}</p>
      )}
    </motion.div>
  );
}

/* ═══════════════════════════════════════════════════════════
   Hero demo — a looping "ask a question, get an answer" panel.
   This is the fastest way to explain what the product actually
   does; a paragraph of copy can't show the shape of the output.
   ═══════════════════════════════════════════════════════════ */

const DEMOS = [
  {
    q: "Which module is blocking the release?",
    answer:
      "Payments is your risk: 12 of 18 failures sit there, all since build #142.",
    bars: [
      { label: "Payments", value: 12, tone: "danger" as const },
      { label: "Auth", value: 4, tone: "warn" as const },
      { label: "Search", value: 2, tone: "ok" as const },
    ],
    verdict: { text: "No-Go", tone: "danger" as const },
  },
  {
    q: "How did the pass rate move this week?",
    answer:
      "Up 6.4 points — 88.1% to 94.5% across five builds, driven by the API suite.",
    bars: [
      { label: "Mon", value: 6, tone: "warn" as const },
      { label: "Wed", value: 9, tone: "ok" as const },
      { label: "Fri", value: 12, tone: "ok" as const },
    ],
    verdict: { text: "Improving", tone: "ok" as const },
  },
  {
    q: "Show me the flakiest tests.",
    answer:
      "3 tests flipped result without a code change — checkout_timeout leads at 7 flips.",
    bars: [
      { label: "checkout", value: 7, tone: "danger" as const },
      { label: "login_sso", value: 5, tone: "warn" as const },
      { label: "cart_sync", value: 3, tone: "warn" as const },
    ],
    verdict: { text: "3 flaky", tone: "warn" as const },
  },
];

const TONE_BAR: Record<string, string> = {
  danger: "from-rose-500 to-red-500",
  warn: "from-amber-400 to-orange-500",
  ok: "from-emerald-400 to-teal-500",
};

const TONE_CHIP: Record<string, string> = {
  danger: "text-rose-500 bg-rose-500/10 border-rose-500/30",
  warn: "text-amber-500 bg-amber-500/10 border-amber-500/30",
  ok: "text-emerald-500 bg-emerald-500/10 border-emerald-500/30",
};

function HeroDemo() {
  const reduce = useReducedMotion();
  const [index, setIndex] = useState(0);
  // "typing" → question is being written, "thinking" → spinner,
  // "answered" → answer + chart on screen.
  const [stage, setStage] = useState<"typing" | "thinking" | "answered">("typing");
  const [typed, setTyped] = useState("");

  const demo = DEMOS[index];

  useEffect(() => {
    if (reduce) {
      // No typewriter for reduced-motion visitors: show the finished state
      // of the first example and leave it there.
      setTyped(DEMOS[0].q);
      setStage("answered");
      return;
    }

    let cancelled = false;
    const timers: ReturnType<typeof setTimeout>[] = [];
    const at = (ms: number, fn: () => void) => {
      timers.push(setTimeout(() => !cancelled && fn(), ms));
    };

    setTyped("");
    setStage("typing");

    const perChar = 38;
    for (let i = 1; i <= demo.q.length; i++) {
      at(i * perChar, () => setTyped(demo.q.slice(0, i)));
    }
    const typedAt = demo.q.length * perChar;
    at(typedAt + 350, () => setStage("thinking"));
    at(typedAt + 1500, () => setStage("answered"));
    at(typedAt + 5200, () => setIndex((n) => (n + 1) % DEMOS.length));

    return () => {
      cancelled = true;
      timers.forEach(clearTimeout);
    };
  }, [index, demo.q, reduce]);

  const maxBar = Math.max(...demo.bars.map((b) => b.value));

  return (
    <motion.div
      initial={{ opacity: 0, y: 30 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.7, delay: 0.4 }}
      className="relative mx-auto mt-16 w-full max-w-2xl"
    >
      {/* glow behind the panel */}
      <div className="absolute -inset-4 rounded-3xl bg-gradient-to-r from-cyan-500/10 via-blue-500/10 to-purple-500/10 blur-2xl" />

      <div className="relative overflow-hidden rounded-2xl border border-slate-200 bg-white/90 shadow-[0_20px_60px_rgba(15,23,42,0.12)] backdrop-blur-xl dark:border-white/[0.08] dark:bg-black/70 dark:shadow-[0_20px_60px_rgba(0,0,0,0.6)]">
        {/* window chrome */}
        <div className="flex items-center gap-2 border-b border-slate-200 px-4 py-3 dark:border-white/[0.06]">
          <span className="h-2.5 w-2.5 rounded-full bg-rose-400/70" />
          <span className="h-2.5 w-2.5 rounded-full bg-amber-400/70" />
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-400/70" />
          <span className="ml-2 text-[11px] font-medium text-slate-400 dark:text-white/30">
            Sentinel · Build #147
          </span>
          <span className="ml-auto flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-500">
            <span className="relative flex h-1.5 w-1.5">
              {!reduce && (
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
              )}
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
            </span>
            Live
          </span>
        </div>

        <div className="min-h-[268px] space-y-4 p-5 text-left">
          {/* question */}
          <div className="flex justify-end">
            <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-gradient-to-r from-cyan-500 to-blue-600 px-4 py-2.5 text-sm font-medium text-white shadow-lg">
              {typed}
              {stage === "typing" && !reduce && (
                <motion.span
                  className="ml-0.5 inline-block h-4 w-[2px] translate-y-0.5 bg-white"
                  animate={{ opacity: [1, 0, 1] }}
                  transition={{ duration: 0.9, repeat: Infinity }}
                />
              )}
            </div>
          </div>

          {/* thinking */}
          {stage === "thinking" && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex items-center gap-2 text-xs text-slate-400 dark:text-white/35"
            >
              <Search className="h-3.5 w-3.5 text-cyan-500" />
              <span>Reading 4,182 test results…</span>
              <span className="flex gap-1">
                {[0, 1, 2].map((i) => (
                  <motion.span
                    key={i}
                    className="h-1 w-1 rounded-full bg-cyan-500"
                    animate={{ opacity: [0.2, 1, 0.2] }}
                    transition={{ duration: 1, delay: i * 0.18, repeat: Infinity }}
                  />
                ))}
              </span>
            </motion.div>
          )}

          {/* answer */}
          {stage === "answered" && (
            <motion.div
              initial={reduce ? false : { opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4 }}
              className="space-y-3"
            >
              <div className="flex gap-2.5">
                <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-gradient-to-br from-cyan-500 to-blue-600">
                  <Sparkles className="h-3 w-3 text-white" />
                </div>
                <p className="text-sm leading-relaxed text-slate-700 dark:text-white/70">
                  {demo.answer}
                </p>
              </div>

              {/* auto-generated chart */}
              <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-4 dark:border-white/[0.06] dark:bg-white/[0.02]">
                <div className="mb-3 flex items-center justify-between">
                  <span className="text-[10px] font-semibold uppercase tracking-widest text-slate-400 dark:text-white/30">
                    Auto-generated
                  </span>
                  <span
                    className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${TONE_CHIP[demo.verdict.tone]}`}
                  >
                    {demo.verdict.text}
                  </span>
                </div>
                <div className="space-y-2">
                  {demo.bars.map((bar, i) => (
                    <div key={bar.label} className="flex items-center gap-3">
                      <span className="w-20 shrink-0 truncate text-[11px] text-slate-500 dark:text-white/40">
                        {bar.label}
                      </span>
                      <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-200 dark:bg-white/[0.06]">
                        <motion.div
                          className={`h-full rounded-full bg-gradient-to-r ${TONE_BAR[bar.tone]}`}
                          initial={reduce ? false : { width: 0 }}
                          animate={{ width: `${(bar.value / maxBar) * 100}%` }}
                          transition={{ duration: 0.7, delay: 0.15 + i * 0.1, ease: [0.22, 1, 0.36, 1] }}
                        />
                      </div>
                      <span className="w-6 shrink-0 text-right font-mono text-[11px] tabular-nums text-slate-500 dark:text-white/40">
                        {bar.value}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </motion.div>
          )}
        </div>

        {/* fake composer, purely to frame the panel as a chat surface */}
        <div className="flex items-center gap-2 border-t border-slate-200 px-4 py-3 dark:border-white/[0.06]">
          <div className="flex-1 truncate text-xs text-slate-300 dark:text-white/20">
            Ask anything about this build…
          </div>
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-r from-cyan-500 to-blue-600">
            <Send className="h-3.5 w-3.5 text-white" />
          </div>
        </div>
      </div>

      {/* which example is playing */}
      <div className="mt-5 flex items-center justify-center gap-2">
        {DEMOS.map((_, i) => (
          <button
            key={i}
            onClick={() => setIndex(i)}
            aria-label={`Show example ${i + 1}`}
            className={`h-1.5 rounded-full transition-all ${
              i === index
                ? "w-7 bg-cyan-500"
                : "w-1.5 bg-slate-300 hover:bg-slate-400 dark:bg-white/15 dark:hover:bg-white/30"
            }`}
          />
        ))}
      </div>
    </motion.div>
  );
}

/* ═══════════════════════════════════════════════════════════
   Page
   ═══════════════════════════════════════════════════════════ */

export default function LandingPage() {
  const [launchHref, setLaunchHref] = useState("/login");
  const reduce = useReducedMotion();

  // Lazy spotlight that trails the cursor across the hero.
  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);
  const smoothX = useSpring(mouseX, { stiffness: 20, damping: 25, mass: 1 });
  const smoothY = useSpring(mouseY, { stiffness: 20, damping: 25, mass: 1 });
  const spotlight = useMotionTemplate`radial-gradient(600px circle at ${smoothX}px ${smoothY}px, rgba(0,240,255,0.07), transparent 60%)`;

  useEffect(() => {
    if (reduce) return;
    mouseX.set(window.innerWidth / 2);
    mouseY.set(window.innerHeight / 2);
    const handler = (e: MouseEvent) => {
      mouseX.set(e.clientX);
      mouseY.set(e.clientY);
    };
    window.addEventListener("mousemove", handler);
    return () => window.removeEventListener("mousemove", handler);
  }, [mouseX, mouseY, reduce]);

  useEffect(() => {
    if (localStorage.getItem("token")) setLaunchHref("/dashboard");
  }, []);

  return (
    <div className="min-h-screen overflow-x-hidden bg-[var(--background)] text-[var(--foreground)] selection:bg-cyan-500/30">
      <Ambience />

      {/* ══════════ NAV ══════════ */}
      <motion.nav
        initial={{ y: -40, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.6 }}
        className="fixed inset-x-0 top-0 z-50 border-b border-slate-200 bg-white/80 backdrop-blur-xl dark:border-white/[0.06] dark:bg-black/60"
      >
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-2">
            <BrandLogo size={34} />
            <span className="flex items-baseline gap-1.5 text-lg font-bold tracking-tight">
              <TestrigWordmark className="text-[13px]" />
              <span className="text-cyan-400">Sentinel</span>
            </span>
          </div>
          <div className="hidden items-center gap-7 text-sm text-slate-500 dark:text-white/50 lg:flex">
            {[
              ["Why", "#why"],
              ["Who It's For", "#who"],
              ["What You Can Do", "#features"],
              ["Data Sources", "#sources"],
              ["Value", "#value"],
            ].map(([label, href]) => (
              <a key={href} href={href} className="transition-colors hover:text-cyan-400">
                {label}
              </a>
            ))}
          </div>
          <Link
            href="/login"
            className="rounded-full border border-cyan-500/30 px-5 py-2 text-sm font-medium text-cyan-400 transition-all hover:border-cyan-400/50 hover:bg-cyan-500/10 hover:shadow-[0_0_20px_rgba(0,240,255,0.15)]"
          >
            Sign In
          </Link>
        </div>
      </motion.nav>

      {/* ══════════ HERO ══════════ */}
      <section className="relative pt-32 pb-24 lg:pt-44">
        <motion.div className="pointer-events-none absolute inset-0" style={{ background: spotlight }} />
        <div className="pointer-events-none absolute left-1/4 top-20 h-[500px] w-[500px] rounded-full bg-cyan-500/[0.09] blur-[140px]" />
        <div className="pointer-events-none absolute bottom-0 right-1/4 h-[400px] w-[400px] rounded-full bg-purple-600/[0.08] blur-[120px]" />

        <div className="relative mx-auto max-w-5xl px-6 text-center">
          <motion.div
            initial={{ opacity: 0, y: 24, scale: 0.92 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.6 }}
          >
            <div className="mb-8 inline-flex items-center gap-2 rounded-full border border-cyan-500/30 bg-cyan-50 px-4 py-1.5 text-xs font-semibold uppercase tracking-widest text-cyan-600 shadow-[0_0_20px_rgba(0,240,255,0.15)] backdrop-blur-md dark:bg-white/[0.04] dark:text-cyan-400">
              <Sparkles className="h-3.5 w-3.5 animate-pulse" />
              AI Insight for QA &amp; Release Teams
            </div>
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.1 }}
            className="mb-7 text-5xl font-extrabold leading-[1.05] tracking-tight md:text-7xl"
          >
            <span className="text-slate-900 dark:text-white">Your test data,</span>
            <br />
            <span className="bg-gradient-to-r from-cyan-400 via-blue-400 to-purple-500 bg-clip-text text-transparent drop-shadow-[0_0_40px_rgba(0,240,255,0.4)]">
              finally answerable
            </span>
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.2 }}
            className="mx-auto mb-10 max-w-2xl text-base leading-relaxed text-slate-600 dark:text-white/55 md:text-lg"
          >
            Your team already produces the test results. Sentinel turns them into answers anyone can
            get in seconds — ask a question in plain English and receive the summary, the chart and a
            clear release call. No manual reporting, no waiting on the one person who knows where the
            data lives.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.3 }}
            className="flex flex-col items-center justify-center gap-4 sm:flex-row"
          >
            <Link
              href={launchHref}
              className="group relative inline-flex items-center gap-3 rounded-full bg-gradient-to-r from-cyan-500 to-blue-600 px-8 py-4 font-semibold text-white shadow-[0_0_40px_rgba(0,240,255,0.35)] transition-all hover:-translate-y-0.5 hover:shadow-[0_0_60px_rgba(0,240,255,0.5)]"
            >
              <span className="absolute inset-0 rounded-full bg-gradient-to-r from-cyan-400 to-blue-500 opacity-0 blur-xl transition-opacity group-hover:opacity-100" />
              <span className="relative">Launch Dashboard</span>
              <ArrowRight className="relative h-5 w-5 transition-transform group-hover:translate-x-1" />
            </Link>
            <a
              href="#why"
              className="inline-flex items-center gap-2 rounded-full border border-slate-300 px-6 py-4 text-sm font-medium text-slate-600 transition-all hover:border-slate-400 hover:bg-slate-100 hover:text-slate-900 dark:border-white/10 dark:text-white/60 dark:hover:border-white/20 dark:hover:bg-white/[0.03] dark:hover:text-white"
            >
              See the problem it solves <ChevronRight className="h-4 w-4" />
            </a>
          </motion.div>

          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.7, delay: 0.45 }}
            className="mt-8 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-xs text-slate-500 dark:text-white/35"
          >
            {[
              "Answers in seconds, not afternoons",
              "Built for QA, engineering and leadership",
              "Your data stays in your environment",
            ].map((t) => (
              <span key={t} className="flex items-center gap-1.5">
                <Check className="h-3.5 w-3.5 text-emerald-500" />
                {t}
              </span>
            ))}
          </motion.div>

          <HeroDemo />
        </div>
      </section>

      <NeonDivider />

      {/* ══════════ WHY / PROBLEM ══════════ */}
      <section id="why" className="relative py-24">
        <div className="mx-auto max-w-5xl px-6">
          <SectionHeading
            eyebrow="The Problem"
            title="Test results pile up."
            accent="Answers don't."
            sub="Every team already generates the data. What's missing is the hour nobody has to turn it into something a stakeholder can actually act on."
          />

          <div className="grid gap-6 md:grid-cols-2">
            {/* before */}
            <motion.div
              initial={{ opacity: 0, x: -24 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ duration: 0.5 }}
              className="rounded-2xl border border-rose-500/20 bg-rose-500/[0.03] p-7"
            >
              <div className="mb-5 flex items-center gap-2.5">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-rose-500/10">
                  <X className="h-4 w-4 text-rose-500" />
                </div>
                <h3 className="text-lg font-bold text-slate-900 dark:text-white">Today</h3>
              </div>
              <ul className="space-y-4">
                {problems.map((p) => (
                  <li key={p} className="flex gap-3 text-sm leading-relaxed text-slate-600 dark:text-white/50">
                    <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-rose-500/60" />
                    {p}
                  </li>
                ))}
              </ul>
            </motion.div>

            {/* after */}
            <motion.div
              initial={{ opacity: 0, x: 24 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ duration: 0.5, delay: 0.1 }}
              className="rounded-2xl border border-cyan-500/25 bg-cyan-500/[0.04] p-7 shadow-[0_0_40px_rgba(0,240,255,0.06)]"
            >
              <div className="mb-5 flex items-center gap-2.5">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-cyan-500/10">
                  <Check className="h-4 w-4 text-cyan-500" />
                </div>
                <h3 className="text-lg font-bold text-slate-900 dark:text-white">With Sentinel</h3>
              </div>
              <ul className="space-y-4">
                {solutions.map((s) => (
                  <li key={s} className="flex gap-3 text-sm leading-relaxed text-slate-700 dark:text-white/65">
                    <Check className="mt-0.5 h-4 w-4 shrink-0 text-cyan-500" />
                    {s}
                  </li>
                ))}
              </ul>
            </motion.div>
          </div>
        </div>
      </section>

      {/* ══════════ WHO IT'S FOR ══════════ */}
      <section id="who" className="relative py-24">
        <div className="mx-auto max-w-6xl px-6">
          <SectionHeading
            eyebrow="Who It's For"
            title="One view of quality,"
            accent="four different questions"
            sub="The same test data means something different depending on who's asking. Sentinel answers each of them in their own language."
          />

          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {audiences.map((a, i) => (
              <motion.div
                key={a.title}
                initial={{ opacity: 0, y: 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-60px" }}
                transition={{ duration: 0.45, delay: i * 0.08 }}
                whileHover={reduce ? undefined : { y: -5 }}
                className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm transition-colors hover:border-cyan-500/30 dark:border-white/[0.05] dark:bg-white/[0.02] dark:hover:bg-white/[0.04]"
              >
                <div className="mb-5 flex h-11 w-11 items-center justify-center rounded-xl bg-cyan-500/[0.08] ring-1 ring-inset ring-cyan-500/20">
                  {a.icon}
                </div>
                <h3 className="mb-2 text-base font-semibold text-slate-900 dark:text-white">{a.title}</h3>
                <p className="mb-4 text-sm leading-relaxed text-slate-600 dark:text-white/45">{a.desc}</p>
                <p className="flex items-start gap-2 text-[13px] font-medium leading-snug text-cyan-700 dark:text-cyan-300/80">
                  <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-cyan-500" />
                  {a.win}
                </p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      <NeonDivider />

      {/* ══════════ FEATURES ══════════ */}
      <section id="features" className="relative py-24">
        <div className="pointer-events-none absolute left-1/2 top-0 h-[600px] w-[600px] -translate-x-1/2 rounded-full bg-purple-600/[0.04] blur-[160px]" />

        <div className="relative mx-auto max-w-6xl px-6">
          <SectionHeading
            eyebrow="What You Can Do"
            title="Ask anything."
            accent="Act on the answer."
            sub="Everything a team needs to understand quality — without building a report, learning a tool or booking an analyst."
          />

          <div className="grid gap-6 md:grid-cols-3">
            {features.map((f, i) => (
              <motion.div
                key={f.title}
                initial={{ opacity: 0, y: 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-60px" }}
                transition={{ duration: 0.45, delay: (i % 3) * 0.08 }}
                whileHover={reduce ? undefined : { y: -6 }}
                className="group relative overflow-hidden rounded-2xl border border-slate-200 bg-white p-8 shadow-lg backdrop-blur-sm transition-colors hover:border-cyan-500/30 hover:shadow-[0_0_30px_rgba(0,240,255,0.1)] dark:border-white/[0.05] dark:bg-white/[0.02] dark:hover:bg-white/[0.04]"
              >
                <div className="pointer-events-none absolute -right-20 -top-20 h-40 w-40 rounded-full bg-cyan-500/[0.08] opacity-0 blur-3xl transition-opacity group-hover:opacity-100" />
                <div
                  className={`relative mb-6 flex h-12 w-12 items-center justify-center rounded-xl border border-slate-200 transition-transform group-hover:scale-110 dark:border-white/[0.06] ${f.iconBg}`}
                >
                  {f.icon}
                </div>
                <h3 className="mb-2 text-lg font-semibold text-slate-900 dark:text-white">{f.title}</h3>
                <p className="text-sm leading-relaxed text-slate-600 dark:text-white/45">{f.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      <NeonDivider />

      {/* ══════════ HOW IT WORKS ══════════ */}
      <section id="how-it-works" className="relative py-24">
        <div className="mx-auto max-w-6xl px-6">
          <SectionHeading
            eyebrow="Getting Started"
            title="Four steps to"
            accent="clarity"
            sub="From the results you already have to a decision you can defend in a release meeting."
          />

          <div className="relative grid gap-10 md:grid-cols-4">
            {/* rail linking the step markers */}
            <div className="absolute left-[12%] right-[12%] top-9 hidden h-px bg-gradient-to-r from-cyan-500/0 via-cyan-500/50 to-cyan-500/0 md:block" />
            <div className="absolute left-[12%] right-[12%] top-9 hidden h-px bg-gradient-to-r from-cyan-500/0 via-cyan-500/30 to-cyan-500/0 blur-sm md:block" />

            {steps.map((step, i) => (
              <motion.div
                key={step.num}
                initial={{ opacity: 0, y: 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-60px" }}
                transition={{ duration: 0.45, delay: i * 0.12 }}
                className="relative z-10 text-center"
              >
                <div className="mx-auto mb-5 flex h-[72px] w-[72px] items-center justify-center rounded-full border border-cyan-500/30 bg-white text-2xl font-bold shadow-[0_0_30px_rgba(0,240,255,0.2)] dark:bg-black">
                  <span className="bg-gradient-to-b from-cyan-400 to-blue-600 bg-clip-text text-transparent">
                    {step.num}
                  </span>
                </div>
                <h3 className="mb-2.5 text-lg font-bold text-slate-900 dark:text-white">{step.title}</h3>
                <p className="px-1 text-sm leading-relaxed text-slate-600 dark:text-white/45">
                  {step.desc}
                </p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      <NeonDivider />

      {/* ══════════ DATA SOURCES ══════════ */}
      <section id="sources" className="relative py-24">
        <div className="mx-auto max-w-6xl px-6">
          <SectionHeading
            title="Bring the data"
            accent="you already have"
            sub="Your reports, spreadsheets, systems and live runs — connected in a few clicks. No migration project, no engineering effort, nothing to rebuild."
          />

          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {sources.map((c, i) => (
              <motion.div
                key={c.name}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-60px" }}
                transition={{ duration: 0.4, delay: (i % 3) * 0.07 }}
                whileHover={reduce ? undefined : { y: -4 }}
                className="group rounded-2xl border border-slate-200 bg-white p-6 transition-colors hover:border-cyan-500/30 hover:shadow-[0_0_25px_rgba(0,240,255,0.08)] dark:border-white/[0.05] dark:bg-white/[0.02] dark:hover:bg-white/[0.04]"
              >
                <div className="mb-4 flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-slate-100 transition-transform group-hover:scale-110 dark:bg-white/[0.06]">
                    {c.icon}
                  </div>
                  <h3 className="font-semibold text-slate-900 dark:text-white">{c.name}</h3>
                </div>
                <p className="mb-4 text-sm leading-relaxed text-slate-600 dark:text-white/45">{c.desc}</p>
                <p className="flex items-start gap-2 border-t border-slate-100 pt-3 text-[13px] font-medium leading-snug text-slate-700 dark:border-white/[0.06] dark:text-white/60">
                  <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />
                  {c.win}
                </p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      <NeonDivider />

      {/* ══════════ OUTCOMES ══════════ */}
      <section id="value" className="relative py-24">
        <div className="pointer-events-none absolute left-1/2 top-0 h-[600px] w-[600px] -translate-x-1/2 rounded-full bg-purple-600/[0.04] blur-[160px]" />

        <div className="relative mx-auto max-w-6xl px-6">
          <SectionHeading
            title="Less time reporting."
            accent="Better decisions."
            sub="The value isn't a new dashboard to maintain. It's the hours your team stops spending on analysis, and the releases that stop going out on a hunch."
          />

          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {outcomes.map((o, i) => (
              <motion.div
                key={o.title}
                initial={{ opacity: 0, y: 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-60px" }}
                transition={{ duration: 0.45, delay: i * 0.08 }}
                whileHover={reduce ? undefined : { y: -5 }}
                className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm transition-colors hover:border-cyan-500/30 dark:border-white/[0.05] dark:bg-white/[0.02] dark:hover:bg-white/[0.04]"
              >
                <div className="mb-5 flex h-11 w-11 items-center justify-center rounded-xl bg-cyan-500/[0.08] ring-1 ring-inset ring-cyan-500/20">
                  {o.icon}
                </div>
                <h3 className="mb-2 text-base font-semibold text-slate-900 dark:text-white">{o.title}</h3>
                <p className="text-sm leading-relaxed text-slate-600 dark:text-white/45">{o.desc}</p>
              </motion.div>
            ))}
          </div>

          {/* why AI, and what it costs */}
          <div className="mt-6 grid gap-6 lg:grid-cols-2">
            <motion.div
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ duration: 0.5 }}
              className="rounded-2xl border border-cyan-500/25 bg-cyan-500/[0.04] p-7 shadow-[0_0_40px_rgba(0,240,255,0.06)]"
            >
              <div className="mb-5 flex items-center gap-2.5">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-cyan-500/10">
                  <Sparkles className="h-4 w-4 text-cyan-500" />
                </div>
                <h3 className="text-lg font-bold text-slate-900 dark:text-white">Why AI belongs here</h3>
              </div>
              <ul className="space-y-4">
                {aiValue.map((v) => (
                  <li key={v} className="flex gap-3 text-sm leading-relaxed text-slate-700 dark:text-white/65">
                    <Check className="mt-0.5 h-4 w-4 shrink-0 text-cyan-500" />
                    {v}
                  </li>
                ))}
              </ul>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ duration: 0.5, delay: 0.1 }}
              className="rounded-2xl border border-emerald-500/25 bg-emerald-500/[0.04] p-7"
            >
              <div className="mb-5 flex items-center gap-2.5">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-500/10">
                  <Wallet className="h-4 w-4 text-emerald-500" />
                </div>
                <h3 className="text-lg font-bold text-slate-900 dark:text-white">AI you can budget for</h3>
              </div>
              <ul className="space-y-4">
                {aiEfficiency.map((v) => (
                  <li key={v} className="flex gap-3 text-sm leading-relaxed text-slate-700 dark:text-white/65">
                    <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
                    {v}
                  </li>
                ))}
              </ul>
            </motion.div>
          </div>

          {/* ownership / deployment — deliberately brief */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-60px" }}
            transition={{ duration: 0.5 }}
            className="mt-6 flex flex-col items-start gap-5 rounded-2xl border border-slate-200 bg-white/70 p-7 backdrop-blur-sm md:flex-row md:items-center dark:border-white/[0.06] dark:bg-white/[0.02]"
          >
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-slate-100 dark:bg-white/[0.06]">
              <Lock className="h-5 w-5 text-slate-600 dark:text-white/60" />
            </div>
            <div>
              <h3 className="mb-1.5 text-base font-semibold text-slate-900 dark:text-white">
                Your quality data never leaves your control
              </h3>
              <p className="text-sm leading-relaxed text-slate-600 dark:text-white/45">
                Sentinel runs inside your own environment, so release information, defect detail and
                customer-sensitive test data stay with you — which keeps security review short and
                procurement simple. A single Docker Compose command brings the whole thing up.
              </p>
            </div>
          </motion.div>
        </div>
      </section>

      <NeonDivider />

      {/* ══════════ CTA ══════════ */}
      <section className="relative py-28">
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-cyan-500/[0.05] to-transparent" />
        <div className="relative mx-auto max-w-3xl px-6 text-center">
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-60px" }}
            transition={{ duration: 0.5 }}
          >
            <h2 className="mb-6 text-3xl font-bold md:text-5xl">
              Ready to stop{" "}
              <span className="bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent drop-shadow-[0_0_20px_rgba(0,240,255,0.3)]">
                guessing
              </span>
              ?
            </h2>
            <p className="mx-auto mb-10 max-w-lg text-slate-600 dark:text-white/45">
              Put your existing test data to work. Give every role — from engineer to executive — a
              straight answer about where quality really stands.
            </p>
            <Link
              href={launchHref}
              className="group relative inline-flex items-center gap-3 rounded-full bg-gradient-to-r from-cyan-500 to-blue-600 px-10 py-4 font-semibold text-white shadow-[0_0_50px_rgba(0,240,255,0.35)] transition-all hover:-translate-y-0.5 hover:shadow-[0_0_70px_rgba(0,240,255,0.5)]"
            >
              <span className="absolute inset-0 rounded-full bg-gradient-to-r from-cyan-400 to-blue-500 opacity-0 blur-xl transition-opacity group-hover:opacity-100" />
              <span className="relative">Get Started</span>
              <ArrowRight className="relative h-5 w-5 transition-transform group-hover:translate-x-1" />
            </Link>
          </motion.div>
        </div>
      </section>

      {/* ══════════ FOOTER ══════════ */}
      <footer className="relative z-10 border-t border-slate-200 py-12 dark:border-white/[0.05]">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-6 px-6 md:flex-row">
          <div className="flex items-center gap-2">
            <BrandLogo size={26} />
            <div>
              <p className="flex items-baseline gap-1.5 text-sm font-semibold text-slate-600 dark:text-white/60">
                <TestrigWordmark className="text-[11px]" />
                <span>Sentinel</span>
              </p>
              <p className="text-xs text-slate-500 dark:text-white/35">{BRAND_TAGLINE}</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-center gap-6 text-xs text-slate-600 dark:text-white/40">
            <span>© {new Date().getFullYear()} Testrig Sentinel — Testrig Technologies Pvt. Ltd.</span>
            <a href="#" className="transition-colors hover:text-cyan-400">Privacy</a>
            <a href="#" className="transition-colors hover:text-cyan-400">Terms</a>
          </div>
        </div>
      </footer>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   Content
   ═══════════════════════════════════════════════════════════ */

const problems = [
  "A release is hours away and nobody can say, with evidence, whether it's safe to ship.",
  "Every status update starts with someone exporting results into a spreadsheet by hand.",
  "The same failure means one thing to leadership and something else to the engineer who owns the suite.",
  "Flaky tests hide inside the noise until they take down a release.",
  "Insight depends on the one person who knows where the data lives — and they're on leave.",
];

const solutions = [
  "Ask in plain English and get the answer, the chart and the caveat together.",
  "Summaries and visuals are produced on demand, so there is no weekly reporting chore.",
  "One set of results, role-aware answers: executive risk framing or full engineering detail.",
  "Regressions, flaky tests and recurring patterns are surfaced automatically across builds.",
  "Anyone with a login can self-serve, so analysis stops being a bottleneck.",
];

/* The four roles Sentinel actually ships accounts for. Each card names the
   role, the one question that role opens the dashboard to answer, and what
   they get instead of the work they do today. */
const audiences = [
  {
    icon: <Briefcase className="h-5 w-5 text-cyan-500" />,
    title: "CTO",
    desc: "“Are we safe to ship?” — release risk and quality trend in plain language, no deck required.",
    win: "A defensible go / no-go in one screen",
  },
  {
    icon: <Target className="h-5 w-5 text-cyan-500" />,
    title: "QA Lead",
    desc: "“Where is quality actually weak?” — the modules dragging the pass rate down, ranked by impact.",
    win: "Effort goes where it changes the number",
  },
  {
    icon: <Users className="h-5 w-5 text-cyan-500" />,
    title: "Test Manager",
    desc: "“What do I report this week?” — coverage, pass rate and regressions across builds, on demand.",
    win: "Reporting time collapses to a question",
  },
  {
    icon: <Rocket className="h-5 w-5 text-cyan-500" />,
    title: "SDET",
    desc: "“Why did this fail?” — the failing tests, their errors, the flaky ones and the slowest ones.",
    win: "Straight to the test worth debugging",
  },
];

const features = [
  {
    icon: <MessageSquare className="h-5 w-5 text-cyan-400" />,
    iconBg: "bg-cyan-500/[0.08]",
    title: "Ask in Plain English",
    desc: "Type the question the way you'd say it in a stand-up — \"is the payment module stable?\" — and get a direct, sourced answer.",
  },
  {
    icon: <BarChart3 className="h-5 w-5 text-purple-400" />,
    iconBg: "bg-purple-500/[0.08]",
    title: "Charts & Dashboards On Demand",
    desc: "Presentation-ready visuals come back with the answer, ready to drop straight into a status update or a steering call.",
  },
  {
    icon: <TrendingUp className="h-5 w-5 text-emerald-400" />,
    iconBg: "bg-emerald-500/[0.08]",
    title: "Automatic Trends & Patterns",
    desc: "Recurring failures, regressions and flaky tests are found, explained and ranked for you — with a recommendation on what to fix first.",
  },
  {
    icon: <Users className="h-5 w-5 text-blue-400" />,
    iconBg: "bg-blue-500/[0.08]",
    title: "Answers Shaped For The Reader",
    desc: "Leadership gets risk and release framing. Engineers get the failing tests and the detail. One source of truth, two conversations.",
  },
  {
    icon: <Shield className="h-5 w-5 text-rose-400" />,
    iconBg: "bg-rose-500/[0.08]",
    title: "Go / No-Go You Can Defend",
    desc: "A clear release-readiness verdict, with the failing evidence behind it one click away when someone challenges it.",
  },
  {
    icon: <Zap className="h-5 w-5 text-amber-400" />,
    iconBg: "bg-amber-500/[0.08]",
    title: "Visibility While It's Running",
    desc: "Follow a test run as it happens, so problems surface during execution instead of in tomorrow's report.",
  },
];

const steps = [
  {
    num: "01",
    title: "Connect",
    desc: "Point Sentinel at the results you already produce — a report, a spreadsheet, an existing system or a live run.",
  },
  {
    num: "02",
    title: "Organize",
    desc: "Everything is read and unified for you. No column mapping, no clean-up project, no work for the engineering team.",
  },
  {
    num: "03",
    title: "Ask",
    desc: "Ask the question the way you'd say it out loud. Sentinel picks the right data, the right chart and the right framing.",
  },
  {
    num: "04",
    title: "Decide",
    desc: "Share the summary, the visual and the go / no-go call — already written for whoever is reading it.",
  },
];

const sources = [
  {
    icon: <FileArchive className="h-5 w-5 text-cyan-500" />,
    name: "Automation Reports",
    desc: "The reports your automation suites already publish — results, history and evidence — become something the whole team can question.",
    win: "Existing reports, finally useful",
  },
  {
    icon: <FileSpreadsheet className="h-5 w-5 text-emerald-500" />,
    name: "Exports & Trackers",
    desc: "The exports already circulating over email and chat join the same picture instead of living in someone's downloads folder.",
    win: "No more one-off spreadsheets",
  },
  {
    icon: <FileSpreadsheet className="h-5 w-5 text-green-600" />,
    name: "Excel Workbooks",
    desc: "Workbooks maintained by hand still count. Drop one in and it's answerable alongside everything else.",
    win: "Manual tracking included",
  },
  {
    icon: <Database className="h-5 w-5 text-blue-500" />,
    name: "Existing Databases",
    desc: "Results already stored in your systems are read where they sit — nothing to migrate, nothing to duplicate.",
    win: "No migration project",
  },
  {
    icon: <Globe className="h-5 w-5 text-purple-500" />,
    name: "Reporting Services",
    desc: "Connect the reporting tools and internal services your teams already send results to.",
    win: "Fits your current toolchain",
  },
  {
    icon: <Radio className="h-5 w-5 text-rose-500" />,
    name: "Live Test Runs",
    desc: "Watch quality as a run unfolds, so the picture is current before the run is even finished.",
    win: "Know sooner, react sooner",
  },
];

const outcomes = [
  {
    icon: <Clock className="h-5 w-5 text-cyan-500" />,
    title: "Hours Back Every Week",
    desc: "The export-and-summarize cycle disappears. Questions that used to take an afternoon are answered while the meeting is still running.",
  },
  {
    icon: <Shield className="h-5 w-5 text-cyan-500" />,
    title: "Decisions You Can Defend",
    desc: "Release calls stop being opinion. Every answer carries the data it came from, so nobody has to take it on trust.",
  },
  {
    icon: <TrendingUp className="h-5 w-5 text-cyan-500" />,
    title: "Problems Caught Earlier",
    desc: "Regressions and unstable areas surface as they emerge, when a fix is cheap — not after they've cost you a release.",
  },
  {
    icon: <Wallet className="h-5 w-5 text-cyan-500" />,
    title: "AI Cost You Can Predict",
    desc: "Spend is capped per person and per team, so adopting AI is a known line item rather than an open-ended bill.",
  },
];

const aiValue = [
  "Test data is large, repetitive and dull to read — exactly the work people postpone and AI does instantly.",
  "It reads every result, not the sample someone had time to look at, so nothing quietly gets skipped.",
  "It explains what happened in language a non-technical stakeholder can act on, without a translation layer.",
  "It ranks what matters — the failure blocking the release ahead of the twenty that don't.",
];

const aiEfficiency = [
  "Only the information a question actually needs reaches the model — never your entire dataset.",
  "Repeat and follow-up questions reuse work that's already been done instead of paying for it twice.",
  "Every user and team has a spend limit, so cost can't run away between invoices.",
  "Usage is visible per person and per project, so you can see exactly what AI is costing and why.",
];
