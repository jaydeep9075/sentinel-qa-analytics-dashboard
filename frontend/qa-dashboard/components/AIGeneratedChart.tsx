"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";

const Chart = dynamic(() => import("react-apexcharts"), { ssr: false });

interface AIGeneratedChartProps {
  config: any;
}

export default function AIGeneratedChart({ config }: AIGeneratedChartProps) {
  const [chartConfig, setChartConfig] = useState<any>(null);

  useEffect(() => {
    if (config) {
      setChartConfig(config);
    }
  }, [config]);

  if (!chartConfig) {
    return (
      <div className="h-64 flex items-center justify-center bg-[#0f0f0f] rounded-lg border border-[#2a2a2a]">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
          <p className="text-gray-400 mt-2">Loading chart...</p>
        </div>
      </div>
    );
  }

  const getChartType = () => {
    switch (chartConfig.chart?.type || config.type) {
      case "pie":
      case "donut":
        return "pie";
      case "line":
        return "line";
      case "bar":
        return "bar";
      case "heatmap":
        return "heatmap";
      case "scatter":
        return "scatter";
      case "area":
        return "area";
      default:
        return "bar";
    }
  };

  const series = chartConfig.series || [];
  const options = {
    ...chartConfig.options,
    chart: {
      ...chartConfig.options?.chart,
      type: getChartType(),
      toolbar: {
        show: true,
        tools: {
          download: true,
          selection: true,
          zoom: true,
          pan: true,
        },
        theme: "dark",
      },
      background: "transparent",
      foreColor: "#a0a0a0",
    },
    theme: {
      mode: "dark",
    },
    grid: {
      borderColor: "#2a2a2a",
      strokeDashArray: 3,
    },
    legend: {
      labels: {
        colors: "#e0e0e0",
      },
    },
    xaxis: {
      ...chartConfig.options?.xaxis,
      labels: {
        style: {
          colors: "#a0a0a0",
        },
      },
    },
    yaxis: {
      ...chartConfig.options?.yaxis,
      labels: {
        style: {
          colors: "#a0a0a0",
        },
      },
    },
    tooltip: {
      theme: "dark",
    },
    responsive: [
      {
        breakpoint: 480,
        options: {
          chart: {
            width: "100%",
          },
          legend: {
            position: "bottom",
          },
        },
      },
    ],
  };

  return (
    <div className="w-full h-[400px]">
      {typeof window !== "undefined" && (
        <Chart
          options={options}
          series={series}
          type={getChartType() as any}
          height="100%"
          width="100%"
        />
      )}
    </div>
  );
}
