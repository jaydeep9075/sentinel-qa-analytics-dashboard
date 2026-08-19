"use client";

import { Loader2 } from "lucide-react";

/**
 * The spinner that sits ON TOP of a chart card until Plotly has actually
 * painted a frame.
 *
 * The gap this closes: a chart's request finishing is not the same event as
 * the chart being on screen. Between them sits the Plotly chunk download, the
 * figure theming pass and Plotly's own layout/draw. Hiding the generation
 * spinner at "response received" left that window blank, which reads as
 * "finished, and then a second chart appeared out of nowhere".
 */
export default function ChartLoadingOverlay({
  label = "Rendering chart…",
  compact = false,
}: {
  label?: string;
  compact?: boolean;
}) {
  return (
    <div
      className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 rounded-xl bg-white/75 backdrop-blur-[2px] dark:bg-[#0b0d11]/70"
      role="status"
      aria-live="polite"
    >
      {/* Ghost of the chart being drawn, so the space reads as "a chart is
          coming here" rather than as an empty panel with a spinner in it. */}
      {!compact && (
        <div className="pointer-events-none absolute inset-x-8 bottom-10 top-10 flex items-end justify-center gap-2 opacity-40">
          {[45, 70, 55, 85, 40, 65].map((h, i) => (
            <div
              key={i}
              className={`w-full max-w-[26px] rounded-t-sm skeleton-shimmer skeleton-shimmer-delay-${(i % 6) + 1}`}
              style={{
                height: `${h}%`,
                background:
                  i % 2 === 0
                    ? "linear-gradient(to top, var(--skeleton-bar-cyan-start), var(--skeleton-bar-cyan-end))"
                    : "linear-gradient(to top, var(--skeleton-bar-purple-start), var(--skeleton-bar-purple-end))",
              }}
            />
          ))}
        </div>
      )}

      <div className="relative z-10 flex items-center gap-2 rounded-full border border-cyan-500/25 bg-white/90 px-3.5 py-1.5 shadow-sm dark:border-cyan-400/20 dark:bg-black/70">
        <Loader2 className="h-4 w-4 animate-spin text-cyan-500 dark:text-cyan-400" />
        <span className="text-xs font-medium text-slate-600 dark:text-white/70">{label}</span>
      </div>
    </div>
  );
}
