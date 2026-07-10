"use client";
import dynamic from "next/dynamic";
import type { Data, Layout } from "plotly.js";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

interface PlotlyChartConfig {
  data: Data[];
  layout: Partial<Layout>;
}

interface AIGeneratedChartProps {
  config: unknown;
}

export default function AIGeneratedChart({ config }: AIGeneratedChartProps) {
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
    <div className="w-full h-[400px]">
      <Plot
        data={cfg.data as Data[]}
        layout={cfg.layout as Partial<Layout>}
        config={{ responsive: true, displayModeBar: true }}
        style={{ width: "100%", height: "100%" }}
        useResizeHandler={true}
      />
    </div>
  );
}
