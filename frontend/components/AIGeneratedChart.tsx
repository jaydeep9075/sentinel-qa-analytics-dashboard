"use client";
import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";
import type { Data, Layout } from "plotly.js";
import { Expand, Minimize2, RotateCcw } from "lucide-react";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

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

  useEffect(() => {
    const onFsChange = () => {
      setIsFullscreen(document.fullscreenElement === containerRef.current);
    };
    document.addEventListener("fullscreenchange", onFsChange);
    return () => document.removeEventListener("fullscreenchange", onFsChange);
  }, []);

  const toggleFullscreen = async () => {
    if (!containerRef.current) return;
    if (document.fullscreenElement === containerRef.current) {
      await document.exitFullscreen();
      return;
    }
    await containerRef.current.requestFullscreen();
  };

  const resetChartView = () => {
    if (!containerRef.current) return;
    const resetBtn = containerRef.current.querySelector(
      'a[data-title="Reset axes"]',
    ) as HTMLAnchorElement | null;
    if (resetBtn) {
      resetBtn.click();
      return;
    }

    const autoscaleBtn = containerRef.current.querySelector(
      'a[data-title="Autoscale"]',
    ) as HTMLAnchorElement | null;
    if (autoscaleBtn) autoscaleBtn.click();
  };

  // config should be the full Plotly JSON from fig.to_json()
  // It contains { data: [...], layout: {...} }
  if (!config || typeof config !== "object") {
    console.error("Invalid chart config:", config);
    return (
      <div className="text-red-400 p-4 text-center">Invalid chart data</div>
    );
  }

  // Ensure data and layout exist
  const cfg = config as Partial<PlotlyChartConfig>;

  if (!Array.isArray(cfg.data) || !cfg.layout || typeof cfg.layout !== "object") {
    console.error("Missing data or layout in config:", config);
    return (
      <div className="text-red-400 p-4 text-center">Chart data incomplete</div>
    );
  }

  return (
    <div
      ref={containerRef}
      className={`relative w-full ${isFullscreen ? "h-screen bg-[var(--background)] p-4" : "h-[400px]"}`}
    >
      <div className="absolute right-2 top-2 z-20 flex items-center gap-2">
        <button
          type="button"
          onClick={resetChartView}
          className="rounded-lg border border-slate-300 bg-white/90 p-1.5 text-slate-600 hover:bg-white hover:text-cyan-600 dark:border-white/10 dark:bg-black/60 dark:text-white/70 dark:hover:text-cyan-300"
          aria-label="Reset chart zoom"
          title="Reset zoom"
        >
          <RotateCcw className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={toggleFullscreen}
          className="rounded-lg border border-slate-300 bg-white/90 p-1.5 text-slate-600 hover:bg-white hover:text-cyan-600 dark:border-white/10 dark:bg-black/60 dark:text-white/70 dark:hover:text-cyan-300"
          aria-label={isFullscreen ? "Exit fullscreen" : "Enter fullscreen"}
          title={isFullscreen ? "Exit fullscreen" : "Enter fullscreen"}
        >
          {isFullscreen ? <Minimize2 className="h-4 w-4" /> : <Expand className="h-4 w-4" />}
        </button>
      </div>
      <Plot
        data={cfg.data as Data[]}
        layout={cfg.layout as Partial<Layout>}
        config={{ responsive: true, displayModeBar: true, displaylogo: false, scrollZoom: true }}
        style={{ width: "100%", height: "100%" }}
        useResizeHandler={true}
      />
    </div>
  );
}
