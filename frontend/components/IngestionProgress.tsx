"use client";

import { useEffect, useRef, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import {
  PlugZap,
  DownloadCloud,
  Cpu,
  Boxes,
  FileText,
  Check,
} from "lucide-react";
import type { IngestStatus } from "@/lib/api";

type Phase = NonNullable<IngestStatus["phase"]>;

interface Stage {
  key: string;
  label: string;
  icon: React.ElementType;
  /** Backend phases that light this stage up. */
  phases: Phase[];
  /** Line the wizard shows while this stage is active and the backend
   *  hasn't sent a more specific `phase_detail`. */
  hint: string;
}

const STAGES: Stage[] = [
  { key: "connect", label: "Connect", icon: PlugZap, phases: ["queued", "connecting"], hint: "Opening the source" },
  { key: "fetch", label: "Fetch", icon: DownloadCloud, phases: ["fetching"], hint: "Pulling records from the connector" },
  { key: "process", label: "Process", icon: Cpu, phases: ["processing"], hint: "Parsing, normalizing and embedding" },
  { key: "index", label: "Index", icon: Boxes, phases: ["indexing"], hint: "Building SQL views over the data" },
  { key: "summarize", label: "Summarize", icon: FileText, phases: ["summarizing", "completed"], hint: "Writing the build summary" },
];

const PHASE_TO_STAGE = new Map<Phase, number>(
  STAGES.flatMap((s, i) => s.phases.map((p) => [p, i] as [Phase, number])),
);

/**
 * Time-based stage guess, used only when the backend sends no `phase`.
 *
 * A backend older than phase tracking (or a job whose status file was
 * written by one) still returns plain running/completed, and a pipeline
 * frozen on "Connect" for three minutes looks broken. These thresholds are
 * a rough shape of a typical run, not a measurement — hence `isEstimated`,
 * which the caller surfaces so nobody reads the bar as ground truth.
 */
function estimateStage(elapsedSeconds: number): number {
  if (elapsedSeconds < 3) return 0;
  if (elapsedSeconds < 8) return 1;
  if (elapsedSeconds < 45) return 2;
  if (elapsedSeconds < 60) return 3;
  return 4;
}

/** Eases a number toward its target so the row counter climbs instead of
 *  jumping — ingestion reports rows in large per-dataset batches. */
function useCountUp(target: number, enabled: boolean): number {
  const [display, setDisplay] = useState(target);
  const frame = useRef<number | undefined>(undefined);

  useEffect(() => {
    // When disabled the caller gets `target` straight back (see the return
    // below), so there is nothing to tween.
    if (!enabled) return;
    const start = performance.now();
    const from = display;
    const delta = target - from;
    if (delta === 0) return;

    const tick = (now: number) => {
      const t = Math.min((now - start) / 700, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      setDisplay(Math.round(from + delta * eased));
      if (t < 1) frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
    return () => {
      if (frame.current !== undefined) cancelAnimationFrame(frame.current);
    };
    // `display` is intentionally omitted: including it restarts the tween on
    // every animated frame, which never converges.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, enabled]);

  return enabled ? display : target;
}

interface Props {
  phase?: Phase;
  detail?: string;
  rows?: number;
  elapsedSeconds: number;
  /** Renders every stage complete and stops the motion. */
  done?: boolean;
}

export default function IngestionProgress({ phase, detail, rows = 0, elapsedSeconds, done = false }: Props) {
  const reduceMotion = useReducedMotion();

  const isEstimated = !phase;
  const activeIndex = done
    ? STAGES.length - 1
    : phase
      ? PHASE_TO_STAGE.get(phase) ?? 0
      : estimateStage(elapsedSeconds);

  const displayRows = useCountUp(rows, !reduceMotion);

  // The bar fills to the middle of the active stage rather than its start,
  // so a long "Process" stage still reads as forward motion.
  const progress = done
    ? 1
    : (activeIndex + 0.5) / STAGES.length;

  const activeStage = STAGES[activeIndex];
  const activeText = done
    ? "Finishing up"
    : detail?.trim() || activeStage.hint;

  return (
    <div className="w-full">
      {/* ── pipeline rail ── */}
      <div className="relative px-1">
        {/* base rail */}
        <div className="absolute left-[calc(10%+2px)] right-[calc(10%+2px)] top-5 h-[2px] rounded-full bg-slate-200 dark:bg-white/[0.08]" />
        {/* filled rail */}
        <motion.div
          className="absolute left-[calc(10%+2px)] top-5 h-[2px] rounded-full bg-gradient-to-r from-cyan-500 to-blue-500"
          initial={{ width: 0 }}
          animate={{ width: `calc((80% - 4px) * ${progress})` }}
          transition={{ duration: reduceMotion ? 0 : 0.6, ease: [0.22, 1, 0.36, 1] }}
        />
        {/* data packets flowing along the filled rail — the one purely
            decorative element here, and the thing that makes a 90-second
            wait read as "working" rather than "hung". */}
        {!done && !reduceMotion && (
          <div
            className="pointer-events-none absolute top-[13px] h-[18px] overflow-hidden"
            style={{ left: "calc(10% + 2px)", width: `calc((80% - 4px) * ${progress})` }}
          >
            {[0, 1, 2].map((i) => (
              <motion.span
                key={i}
                className="absolute top-[7px] h-1 w-1 rounded-full bg-cyan-300 shadow-[0_0_8px_2px_rgba(34,211,238,0.7)]"
                initial={{ left: "-4%" }}
                animate={{ left: "104%" }}
                transition={{
                  duration: 1.8,
                  delay: i * 0.6,
                  repeat: Infinity,
                  ease: "linear",
                }}
              />
            ))}
          </div>
        )}

        <div className="relative grid grid-cols-5">
          {STAGES.map((stage, i) => {
            const isComplete = done || i < activeIndex;
            const isActive = !done && i === activeIndex;
            const Icon = isComplete ? Check : stage.icon;

            return (
              <div key={stage.key} className="flex flex-col items-center gap-2">
                <motion.div
                  className={[
                    "relative flex h-10 w-10 items-center justify-center rounded-full border-2 transition-colors",
                    isComplete
                      ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-500"
                      : isActive
                        ? "border-cyan-500 bg-cyan-500/10 text-cyan-500"
                        : "border-slate-200 bg-white text-slate-300 dark:border-white/[0.1] dark:bg-white/[0.02] dark:text-white/20",
                  ].join(" ")}
                  animate={
                    isActive && !reduceMotion
                      ? { scale: [1, 1.07, 1] }
                      : { scale: 1 }
                  }
                  transition={{ duration: 1.6, repeat: isActive && !reduceMotion ? Infinity : 0, ease: "easeInOut" }}
                >
                  {/* expanding halo on the active node */}
                  {isActive && !reduceMotion && (
                    <motion.span
                      className="absolute inset-0 rounded-full border-2 border-cyan-500"
                      initial={{ opacity: 0.5, scale: 1 }}
                      animate={{ opacity: 0, scale: 1.75 }}
                      transition={{ duration: 1.6, repeat: Infinity, ease: "easeOut" }}
                    />
                  )}
                  <Icon className="h-4 w-4" />
                </motion.div>
                <span
                  className={[
                    "text-[10px] font-semibold uppercase tracking-wider",
                    isComplete
                      ? "text-emerald-600 dark:text-emerald-400"
                      : isActive
                        ? "text-cyan-600 dark:text-cyan-400"
                        : "text-slate-400 dark:text-white/25",
                  ].join(" ")}
                >
                  {stage.label}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── live status line ── */}
      <div className="mt-5 rounded-lg border border-slate-200 bg-slate-50/70 px-3 py-2.5 dark:border-white/[0.07] dark:bg-white/[0.02]">
        <div className="flex items-center justify-between gap-3">
          <motion.p
            // Keyed on the text so each new stage message crossfades in
            // rather than swapping abruptly mid-run.
            key={activeText}
            initial={reduceMotion ? false : { opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
            className="truncate text-xs font-medium text-slate-700 dark:text-white/70"
          >
            {activeText}
          </motion.p>
          <span className="shrink-0 font-mono text-[11px] tabular-nums text-slate-400 dark:text-white/30">
            {elapsedSeconds}s
          </span>
        </div>

        {displayRows > 0 && (
          <p className="mt-1 text-[11px] text-slate-500 dark:text-white/40">
            <span className="font-mono tabular-nums text-cyan-600 dark:text-cyan-400">
              {displayRows.toLocaleString()}
            </span>{" "}
            rows ingested
          </p>
        )}

        {isEstimated && !done && (
          <p className="mt-1 text-[10px] text-slate-400 dark:text-white/25">
            Stage is estimated — this backend doesn&rsquo;t report pipeline phases.
          </p>
        )}
      </div>
    </div>
  );
}
