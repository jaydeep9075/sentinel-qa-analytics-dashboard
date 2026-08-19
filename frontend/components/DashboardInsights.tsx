"use client";

import { motion } from "framer-motion";
import {
  AlertOctagon,
  CheckCircle2,
  Clock3,
  HelpCircle,
  Layers,
  ShieldAlert,
  Timer,
  TriangleAlert,
} from "lucide-react";
import type { DashboardInsights } from "@/lib/api";

/**
 * The business band under the KPI tiles.
 *
 * It answers the four questions a stakeholder actually opens this page with —
 * can we ship, how much of the product is affected, what is causing it, and
 * what is the suite costing us — instead of restating the raw pass/fail
 * counts that the tiles above already show.
 */

interface Props {
  insights?: DashboardInsights | null;
  qualityScore?: number;
  loading?: boolean;
}

const bandVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.05, delayChildren: 0.02 } },
};

const cardVariants = {
  hidden: { opacity: 0, y: 12 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { type: "spring" as const, stiffness: 300, damping: 28 },
  },
};

/** Seconds → the coarsest unit that still reads honestly at a glance. */
function formatDuration(seconds?: number): string {
  const value = Number(seconds || 0);
  if (!Number.isFinite(value) || value <= 0) return "—";
  if (value < 1) return `${Math.round(value * 1000)}ms`;
  if (value < 60) return `${value.toFixed(value < 10 ? 1 : 0)}s`;
  const minutes = value / 60;
  if (minutes < 60) return `${minutes.toFixed(minutes < 10 ? 1 : 0)}m`;
  const hours = minutes / 60;
  return `${hours.toFixed(hours < 10 ? 1 : 0)}h`;
}

const VERDICT_STYLES: Record<
  string,
  { ring: string; text: string; chip: string; Icon: typeof CheckCircle2 }
> = {
  ready: {
    ring: "border-emerald-500/25",
    text: "text-emerald-600 dark:text-emerald-400",
    chip: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/25",
    Icon: CheckCircle2,
  },
  at_risk: {
    ring: "border-amber-500/25",
    text: "text-amber-600 dark:text-amber-400",
    chip: "bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/25",
    Icon: TriangleAlert,
  },
  blocked: {
    ring: "border-red-500/25",
    text: "text-red-600 dark:text-red-400",
    chip: "bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/25",
    Icon: AlertOctagon,
  },
  unknown: {
    ring: "border-slate-200 dark:border-white/[0.06]",
    text: "text-slate-600 dark:text-white/60",
    chip: "bg-slate-500/10 text-slate-600 dark:text-white/60 border-slate-400/20",
    Icon: HelpCircle,
  },
};

function InsightCard({
  icon: Icon,
  label,
  value,
  valueClass = "text-slate-900 dark:text-white",
  detail,
  accent = "border-slate-200 dark:border-white/[0.06]",
  children,
}: {
  icon: typeof Layers;
  label: string;
  value: string;
  valueClass?: string;
  detail?: string;
  accent?: string;
  children?: React.ReactNode;
}) {
  return (
    <motion.div
      variants={cardVariants}
      className={`rounded-xl border bg-white p-4 transition-colors hover:border-cyan-500/25 dark:bg-white/[0.02] ${accent}`}
    >
      <div className="mb-2 flex items-center gap-1.5">
        <Icon className="h-3.5 w-3.5 text-slate-400 dark:text-white/35" />
        <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500 dark:text-white/35">
          {label}
        </p>
      </div>
      <p className={`truncate text-xl font-bold leading-tight ${valueClass}`} title={value}>
        {value}
      </p>
      {detail && (
        <p className="mt-1.5 line-clamp-2 text-xs leading-snug text-slate-500 dark:text-white/45">
          {detail}
        </p>
      )}
      {children}
    </motion.div>
  );
}

function InsightSkeleton() {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-white/[0.06] dark:bg-white/[0.02]">
      <div className="mb-3 h-2.5 w-24 rounded bg-slate-200 dark:bg-white/10" />
      <div className="h-5 w-32 rounded bg-slate-200 dark:bg-white/10" />
      <div className="mt-2 h-2.5 w-full rounded bg-slate-100 dark:bg-white/[0.06]" />
    </div>
  );
}

export default function DashboardInsightBand({ insights, qualityScore, loading }: Props) {
  if (loading) {
    return (
      <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <InsightSkeleton key={i} />
        ))}
      </div>
    );
  }

  if (!insights?.has_data) return null;

  const verdict = insights.readiness?.verdict || "unknown";
  const style = VERDICT_STYLES[verdict] || VERDICT_STYLES.unknown;

  const blast = insights.blast_radius || {};
  const impacted = Number(blast.impacted || 0);
  const areasTotal = Number(blast.total || 0);
  const blastValue = areasTotal > 0 ? `${impacted} of ${areasTotal} areas` : "—";
  const blastDetail =
    impacted === 0
      ? "No product area is currently failing."
      : blast.top_area
        ? `Worst: ${blast.top_area} (${Number(blast.top_area_failures || 0).toLocaleString()} failing)`
        : `${impacted} area${impacted === 1 ? "" : "s"} affected.`;

  const topFailure = insights.top_failure || {};
  const failureValue = topFailure.signature || "No recurring cause";
  const failureDetail = topFailure.signature
    ? `${Number(topFailure.count || 0).toLocaleString()} tests — ${Number(
        topFailure.share || 0,
      ).toFixed(0)}% of all failures trace to this one cause.`
    : "Failures have no shared error signature — triage individually.";

  const runtime = insights.runtime || {};
  const wasted = Number(runtime.failed_seconds || 0);
  const totalRuntime = Number(runtime.total_seconds || 0);
  const wastedShare = totalRuntime > 0 ? Math.round((wasted / totalRuntime) * 100) : 0;
  const runtimeDetail =
    wasted > 0
      ? `${formatDuration(wasted)} (${wastedShare}%) spent on tests that failed${
          runtime.slowest_area ? ` · slowest area: ${runtime.slowest_area}` : ""
        }`
      : `Average ${formatDuration(runtime.avg_seconds)} per test${
          runtime.slowest_area ? ` · slowest area: ${runtime.slowest_area}` : ""
        }`;

  const score = Math.max(0, Math.min(100, Math.round(Number(qualityScore || 0))));

  return (
    <motion.div
      variants={bandVariants}
      initial="hidden"
      animate="visible"
      className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4"
    >
      {/* Ship / don't ship — the only card that carries colour by default,
          because it is the one decision the page exists to support. */}
      <InsightCard
        icon={style.Icon}
        label="Release Readiness"
        value={insights.readiness?.label || "Unknown"}
        valueClass={style.text}
        detail={insights.readiness?.detail}
        accent={style.ring}
      >
        <div className="mt-3 flex items-center gap-2">
          <span
            className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${style.chip}`}
          >
            {Number(insights.pass_rate || 0).toFixed(1)}% pass
          </span>
          {score > 0 && (
            <span
              className="rounded-full border border-slate-300 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500 dark:border-white/10 dark:text-white/45"
              title="How complete and well-formed this build's ingested data is"
            >
              {score}% data quality
            </span>
          )}
        </div>
      </InsightCard>

      <InsightCard
        icon={Layers}
        label="Failure Blast Radius"
        value={blastValue}
        detail={blastDetail}
      />

      <InsightCard
        icon={ShieldAlert}
        label="Top Failure Driver"
        value={failureValue}
        detail={failureDetail}
      />

      <InsightCard
        icon={Timer}
        label="Suite Runtime"
        value={formatDuration(totalRuntime)}
        detail={runtimeDetail}
      >
        {Number(insights.coverage?.skipped || 0) > 0 && (
          <p className="mt-3 flex items-center gap-1.5 text-[11px] text-slate-500 dark:text-white/40">
            <Clock3 className="h-3 w-3" />
            {Number(insights.coverage?.skipped || 0).toLocaleString()} skipped (
            {Number(insights.coverage?.skipped_rate || 0).toFixed(1)}% coverage gap)
          </p>
        )}
      </InsightCard>
    </motion.div>
  );
}
