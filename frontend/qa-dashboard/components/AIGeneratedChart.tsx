"use client";
import dynamic from "next/dynamic";

const Chart = dynamic(() => import("react-apexcharts"), { ssr: false });

export default function AIGeneratedChart({ config }: { config: any }) {
  if (!config) {
    return (
      <div className="text-gray-500 p-4 text-center">
        No chart data available
      </div>
    );
  }

  const chartType = config.chart?.type || config.type || "bar";
  const isPie = chartType === "pie";

  // Build series and options
  let series: any[] = [];
  let options: any = {
    chart: {
      type: chartType,
      height: config.chart?.height || 350,
      background: "transparent",
      foreColor: "#a0a0a0",
      toolbar: { show: true },
    },
    title: config.title || { text: "Chart", align: "center" },
    grid: { borderColor: "#2a2a2a" },
    tooltip: { theme: "dark" },
    theme: { mode: "dark" },
    dataLabels: { enabled: true },
  };

  // Determine series structure
  if (config.series) {
    if (Array.isArray(config.series)) {
      if (isPie && !config.series[0]?.data) {
        // Pie: series is array of numbers
        series = config.series;
        options.labels = config.labels || [];
      } else if (config.series[0]?.data) {
        // Bar/line: series array of objects with name and data
        series = config.series;
        if (config.xaxis) options.xaxis = config.xaxis;
        if (config.yaxis) options.yaxis = config.yaxis;
      } else {
        // Fallback: treat as numbers
        series = config.series;
      }
    }
  } else if (config.data && Array.isArray(config.data)) {
    series = [{ name: "Data", data: config.data }];
  } else {
    // Ultimate fallback
    series = [{ name: "Data", data: [1] }];
    options.xaxis = { categories: ["No data"] };
  }

  // Ensure pie has labels
  if (isPie && series.length && !options.labels) {
    if (config.labels) {
      options.labels = config.labels;
    } else {
      options.labels = series.map((_: any, i: number) => `Item ${i + 1}`);
    }
  }

  if (config.colors) options.colors = config.colors;

  if (!series || (Array.isArray(series) && series.length === 0)) {
    return (
      <div className="text-gray-500 p-4 text-center">Invalid chart data</div>
    );
  }

  return (
    <div className="w-full h-[350px]">
      <Chart options={options} series={series} type={chartType} height="100%" />
    </div>
  );
}
