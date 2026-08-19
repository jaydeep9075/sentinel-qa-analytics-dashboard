"use client";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Data, Layout } from "plotly.js";
import { Expand, Minimize2, Table2, BarChart3 } from "lucide-react";
import { useTheme } from "@/lib/theme";
import { themeFigure, readSentinelMeta } from "@/lib/chartTheme";
import { preloadPlotly } from "@/lib/plotlyPreload";
import ChartLoadingOverlay from "./ChartLoadingOverlay";

// No `loading` fallback here on purpose: the `painted` overlay below already
// covers this window (Plot has not mounted, so it cannot have reported a
// paint), and it covers the longer window after the chunk lands while Plotly
// is still drawing. One overlay spanning both is what makes the wait read as
// a single continuous "chart is coming" rather than two flickers.
const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

// Belt-and-braces: if Plotly never reports back (an unsupported trace, a
// throw inside its draw loop), the overlay must not sit there forever
// claiming the chart is still coming.
const PAINT_TIMEOUT_MS = 12000;

interface PlotlyChartConfig {
  data: Data[];
  layout: Partial<Layout>;
}

interface AIGeneratedChartProps {
  config: unknown;
}

export default function AIGeneratedChart({ config }: AIGeneratedChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showTable, setShowTable] = useState(false);
  // Which figure Plotly has actually drawn. Storing the config itself rather
  // than a boolean means a new figure resets the overlay during render — no
  // effect, and no frame in which the previous chart shows through as if it
  // were the new one.
  const [paintedConfig, setPaintedConfig] = useState<unknown>(null);
  const painted = paintedConfig === config;
  const renderStartRef = useRef<number>(0);
  const { isDark } = useTheme();

  useEffect(() => {
    renderStartRef.current =
      typeof performance !== "undefined" && typeof performance.now === "function"
        ? performance.now()
        : Date.now();
    void preloadPlotly().catch(() => {});
  }, [config]);

  useEffect(() => {
    if (painted) return;
    const timer = window.setTimeout(() => setPaintedConfig(config), PAINT_TIMEOUT_MS);
    return () => window.clearTimeout(timer);
  }, [painted, config]);

  const handlePainted = useCallback(() => {
    if (typeof window !== "undefined") {
      // Plotly resolves onInitialized once the DOM is written, but before the
      // browser has composited it. Waiting a frame means the overlay lifts on
      // a chart that is genuinely visible, not one that is about to be.
      window.requestAnimationFrame(() => setPaintedConfig(config));
    } else {
      setPaintedConfig(config);
    }

    if (typeof window === "undefined") return;
    const enabled =
      process.env.NODE_ENV !== "production" || localStorage.getItem("qa_perf_debug") === "1";
    if (!enabled) return;
    const now =
      typeof performance !== "undefined" && typeof performance.now === "function"
        ? performance.now()
        : Date.now();
    console.debug("[perf] chart:render", {
      render_ms: Number((now - renderStartRef.current).toFixed(1)),
    });
  }, [config]);

  useEffect(() => {
    const onFsChange = () => {
      setIsFullscreen(document.fullscreenElement === containerRef.current);
    };
    document.addEventListener("fullscreenchange", onFsChange);
    return () => document.removeEventListener("fullscreenchange", onFsChange);
  }, []);

  const cfg = config as Partial<PlotlyChartConfig> | null;
  const rawData = Array.isArray(cfg?.data) ? cfg.data : null;
  const rawLayout =
    cfg?.layout && typeof cfg.layout === "object" ? (cfg.layout as Partial<Layout>) : null;

  // Re-derive rather than mutate, so toggling the theme back and forth can't
  // accumulate drift in the figure we were handed.
  const themed = useMemo(() => {
    if (!rawData || !rawLayout) return null;
    return themeFigure(
      rawData as unknown[],
      rawLayout as Record<string, unknown>,
      isDark ? "dark" : "light",
    );
  }, [rawData, rawLayout, isDark]);

  const meta = useMemo(() => (rawLayout ? readSentinelMeta(rawLayout) : null), [rawLayout]);
  const table = meta?.table;

  const toggleFullscreen = async () => {
    if (!containerRef.current) return;
    if (document.fullscreenElement === containerRef.current) {
      await document.exitFullscreen();
      return;
    }
    await containerRef.current.requestFullscreen();
  };

  if (!config || typeof config !== "object") {
    console.error("Invalid chart config:", config);
    return <div className="text-red-400 p-4 text-center">Invalid chart data</div>;
  }

  if (!rawData || !rawLayout || !themed) {
    console.error("Missing data or layout in config:", config);
    return <div className="text-red-400 p-4 text-center">Chart data incomplete</div>;
  }

  // One segmented control rather than two floating chips: with Plotly's own
  // modebar gone, these two are the entire chart toolbar, and grouping them
  // keeps a single, predictable hit area in the corner of every card.
  const buttonClass =
    "flex items-center justify-center rounded-md p-1.5 text-slate-500 transition-colors hover:bg-slate-100 hover:text-cyan-600 dark:text-white/55 dark:hover:bg-white/10 dark:hover:text-cyan-300";

  return (
    <div
      ref={containerRef}
      className={`relative w-full ${
        isFullscreen ? "h-screen overflow-auto bg-[var(--background)] p-4" : "h-[400px]"
      }`}
    >
      <div className="absolute right-2 top-2 z-20 flex items-center gap-0.5 rounded-lg border border-slate-200 bg-white/85 p-0.5 shadow-sm backdrop-blur-sm dark:border-white/10 dark:bg-black/60">
        {table && table.rows.length > 0 && (
          <button
            type="button"
            onClick={() => setShowTable((v) => !v)}
            className={buttonClass}
            aria-label={showTable ? "Show chart" : "Show data table"}
            title={showTable ? "Show chart" : "Show data table"}
          >
            {showTable ? <BarChart3 className="h-4 w-4" /> : <Table2 className="h-4 w-4" />}
          </button>
        )}
        <button
          type="button"
          onClick={toggleFullscreen}
          className={buttonClass}
          aria-label={isFullscreen ? "Exit fullscreen" : "Enter fullscreen"}
          title={isFullscreen ? "Exit fullscreen" : "Enter fullscreen"}
        >
          {isFullscreen ? <Minimize2 className="h-4 w-4" /> : <Expand className="h-4 w-4" />}
        </button>
      </div>

      {showTable && table ? (
        /* The table view is the chart's WCAG-clean twin: every plotted value as
           text, so no value is reachable only through colour or a hover. */
        <div className="h-full overflow-auto pt-10">
          <table className="w-full border-collapse text-left text-xs tabular-nums">
            <thead className="sticky top-0 bg-white dark:bg-[#16181d]">
              <tr>
                {table.columns.map((col) => (
                  <th
                    key={col.key}
                    scope="col"
                    className="border-b border-slate-200 px-3 py-2 font-semibold text-slate-700 dark:border-white/10 dark:text-white/80"
                  >
                    {col.label}
                    {col.unit ? ` (${col.unit})` : ""}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {table.rows.map((row, i) => (
                <tr key={i} className="odd:bg-slate-50/60 dark:odd:bg-white/[0.03]">
                  {row.map((cell, j) => (
                    <td
                      key={j}
                      className="border-b border-slate-100 px-3 py-1.5 text-slate-600 dark:border-white/5 dark:text-white/70"
                    >
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {meta?.truncated && (
            <p className="px-3 py-2 text-xs text-slate-500 dark:text-white/50">
              Showing the charted subset{meta.row_count ? ` of ${meta.row_count} rows` : ""}.
            </p>
          )}
        </div>
      ) : (
        <>
          {/* The chart is mounted underneath the overlay rather than after
              it: Plotly needs a real, sized container to draw into, so
              gating the mount on "loading finished" would deadlock the very
              paint we are waiting for. Fading in instead of toggling
              `display` keeps the container measurable throughout. */}
          <div
            className="h-full w-full transition-opacity duration-300 ease-out"
            style={{ opacity: painted ? 1 : 0 }}
            aria-busy={!painted}
          >
            <Plot
              data={themed.data as Data[]}
              layout={themed.layout as Partial<Layout>}
              config={{
                responsive: true,
                // Plotly draws its own modebar in the top-right corner of
                // the plot — exactly where this card's own controls sit —
                // so the two stacks overlapped. The card's controls win:
                // they are the only two actions worth offering (read the
                // numbers, or see the figure bigger), and hiding the
                // modebar removes the download/zoom/pan/lasso row that was
                // colliding with them.
                displayModeBar: false,
                displaylogo: false,
                scrollZoom: false,
                doubleClick: false,
              }}
              style={{ width: "100%", height: "100%" }}
              useResizeHandler={true}
              onInitialized={handlePainted}
              onError={() => setPaintedConfig(config)}
            />
          </div>
          {!painted && <ChartLoadingOverlay />}
        </>
      )}
    </div>
  );
}
