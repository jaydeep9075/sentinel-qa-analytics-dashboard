"use client";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";

// Dynamically import react-plotly.js to avoid SSR issues
const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

interface AIGeneratedChartProps {
  config: any;
}

export default function AIGeneratedChart({ config }: AIGeneratedChartProps) {
  const [isClient, setIsClient] = useState(false);

  useEffect(() => {
    setIsClient(true);
  }, []);

  if (!config || !config.data || !isClient) {
    return <div className="text-gray-500 p-4 text-center">No chart data</div>;
  }

  // config already has data and layout (from fig.to_json())
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