"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

/**
 * A static "Thinking..." gives the reader no way to tell a slow answer from a
 * stuck one, so every second past the first feels like a failure. These stages
 * are not decoration: they name the actual steps `handlers.handle_chat` runs
 * in order — read the question, query DuckDB, write the answer, check the
 * figures against the data — so the label on screen is a genuine (if
 * time-estimated) report of where the request is.
 */
const STAGES: { at: number; label: string }[] = [
  { at: 0, label: "Reading your question…" },
  { at: 1200, label: "Querying the test data…" },
  { at: 4000, label: "Writing the answer…" },
  { at: 9000, label: "Checking every figure against the data…" },
  { at: 16000, label: "Almost there — this one's a big result set…" },
];

export default function ThinkingIndicator({ label }: { label?: string }) {
  const [stage, setStage] = useState(0);

  useEffect(() => {
    if (label) return;
    const timers = STAGES.slice(1).map((s, i) =>
      window.setTimeout(() => setStage(i + 1), s.at),
    );
    return () => timers.forEach((t) => window.clearTimeout(t));
  }, [label]);

  const text = label || STAGES[stage].label;

  return (
    <div className="flex justify-start">
      <div className="flex items-center gap-2.5 rounded-2xl rounded-tl-sm border border-slate-200 bg-slate-100 px-4 py-2.5 dark:border-white/[0.06] dark:bg-white/[0.04]">
        <Loader2 className="h-4 w-4 animate-spin text-cyan-400" />
        <span
          key={text}
          className="animate-[fadeIn_240ms_ease-out] text-sm text-slate-500 dark:text-white/40"
        >
          {text}
        </span>
        <span className="flex gap-1" aria-hidden="true">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="h-1 w-1 animate-bounce rounded-full bg-cyan-400/70"
              style={{ animationDelay: `${i * 140}ms`, animationDuration: "1s" }}
            />
          ))}
        </span>
      </div>
    </div>
  );
}
