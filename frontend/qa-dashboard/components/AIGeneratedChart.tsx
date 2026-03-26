"use client";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";

const Chart = dynamic(() => import("react-apexcharts"), { ssr: false });

export default function AIGeneratedChart({ config }: { config: any }) {
  if (!config || !config.series) return <div className="text-gray-500">Invalid Chart Data</div>;

  const options = {
    ...config.options,
    chart: {
      ...config.options?.chart,
      background: "transparent",
      foreColor: "#a0a0a0",
      toolbar: { show: true },
    },
    theme: { mode: "dark" },
    grid: { borderColor: "#2a2a2a" },
    tooltip: { theme: "dark" },
  };

  return (
    <div className="w-full h-[350px]">
      <Chart
        options={options}
        series={config.series}
        type={config.type || config.options?.chart?.type || "bar"}
        height="100%"
      />
    </div>
  );
}