"use client";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

interface AIGeneratedChartProps {
  config: any;
}

export default function AIGeneratedChart({ config }: AIGeneratedChartProps) {
  const [isClient, setIsClient] = useState(false);

  useEffect(() => {
    setIsClient(true);
  }, []);

  if (!isClient)
    return (
      <div className="text-gray-500 p-4 text-center">Loading chart...</div>
    );

  // config should be the full Plotly JSON from fig.to_json()
  // It contains { data: [...], layout: {...} }
  if (!config || typeof config !== "object") {
    console.error("Invalid chart config:", config);
    return (
      <div className="text-red-400 p-4 text-center">Invalid chart data</div>
    );
  }

  // Ensure data and layout exist
  if (!config.data || !config.layout) {
    console.error("Missing data or layout in config:", config);
    return (
      <div className="text-red-400 p-4 text-center">Chart data incomplete</div>
    );
  }

  return (
    <div className="w-full h-[400px]">
      <Plot
        data={config.data}
        layout={config.layout}
        config={{ responsive: true, displayModeBar: true }}
        style={{ width: "100%", height: "100%" }}
        useResizeHandler={true}
      />
    </div>
  );
}
