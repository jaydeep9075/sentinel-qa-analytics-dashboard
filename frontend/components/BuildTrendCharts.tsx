"use client";

import React from "react";
import dynamic from "next/dynamic";
import type { ApexOptions } from "apexcharts";

const Chart = dynamic(() => import("react-apexcharts"), { ssr: false });

interface Props {
  chartData: {
    buildNumber: number;
    label: string;
    passRate: number;
    passed: number;
    failed: number;
    totalDuration: number;
    avgDuration: number;
  }[];
}

export default function BuildTrendCharts({ chartData }: Props) {
  if (!chartData || chartData.length === 0) {
    return <div className="p-8 text-center text-red-400">No chart data</div>;
  }

  // Common X-axis categories (Build 1, Build 2, ...)
  const categories = chartData.map(d => d.label);

  // 1. Pass Rate Trend (Line chart)
  const passRateOptions: ApexOptions = {
    chart: { type: "line", height: 350, toolbar: { show: false }, background: "transparent" },
    stroke: { curve: "smooth", width: 3 },
    colors: ["#3b82f6"],
    xaxis: { categories, labels: { style: { colors: "#9ca3af" } } },
    yaxis: { title: { text: "Pass Rate (%)" }, min: 0, max: 100, labels: { style: { colors: "#9ca3af" } } },
    title: { text: "Pass Rate Trend", align: "left", style: { color: "#fff", fontSize: "16px", fontWeight: "600" } },
    tooltip: { theme: "dark", y: { formatter: (val: number) => val.toFixed(1) + "%" } },
    grid: { borderColor: "#374151" },
  };
  const passRateSeries = [{ name: "Pass Rate", data: chartData.map(d => d.passRate) }];

  // 2. Passed vs Failed (Stacked Bar)
  const stackedOptions: ApexOptions = {
    chart: { type: "bar", height: 350, stacked: true, toolbar: { show: false }, background: "transparent" },
    colors: ["#10b981", "#ef4444"],
    xaxis: { categories, labels: { style: { colors: "#9ca3af" } } },
    yaxis: { title: { text: "Number of Tests" }, labels: { style: { colors: "#9ca3af" } } },
    legend: { position: "top", labels: { colors: "#fff" } },
    title: { text: "Test Results Breakdown", align: "left", style: { color: "#fff", fontSize: "16px", fontWeight: "600" } },
    tooltip: { theme: "dark" },
    grid: { borderColor: "#374151" },
  };
  const stackedSeries = [
    { name: "Passed", data: chartData.map(d => d.passed) },
    { name: "Failed", data: chartData.map(d => d.failed) },
  ];

  // 3. Total Duration (Line chart)
  const totalDurationOptions: ApexOptions = {
    chart: { type: "line", height: 350, toolbar: { show: false }, background: "transparent" },
    stroke: { curve: "smooth", width: 3 },
    colors: ["#a855f7"],
    xaxis: { categories, labels: { style: { colors: "#9ca3af" } } },
    yaxis: { title: { text: "Total Duration (seconds)" }, labels: { style: { colors: "#9ca3af" } } },
    title: { text: "Total Duration", align: "left", style: { color: "#fff", fontSize: "16px", fontWeight: "600" } },
    tooltip: { theme: "dark", y: { formatter: (val: number) => val.toFixed(2) + " s" } },
    grid: { borderColor: "#374151" },
  };
  const totalDurationSeries = [{ name: "Total Duration", data: chartData.map(d => d.totalDuration) }];

  // 4. Average Test Duration (Bar chart)
  const avgDurationOptions: ApexOptions = {
    chart: { type: "bar", height: 350, toolbar: { show: false }, background: "transparent" },
    colors: ["#f59e0b"],
    xaxis: { categories, labels: { style: { colors: "#9ca3af" } } },
    yaxis: { title: { text: "Average Duration (seconds)" }, labels: { style: { colors: "#9ca3af" } } },
    title: { text: "Average Test Duration per Build", align: "left", style: { color: "#fff", fontSize: "16px", fontWeight: "600" } },
    tooltip: { theme: "dark", y: { formatter: (val: number) => val.toFixed(2) + " s" } },
    grid: { borderColor: "#374151" },
  };
  const avgDurationSeries = [{ name: "Avg Duration", data: chartData.map(d => d.avgDuration) }];

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div className="bg-white/[0.03] backdrop-blur p-4 rounded-2xl border border-white/10">
        <Chart options={passRateOptions} series={passRateSeries} type="line" height={350} />
      </div>
      <div className="bg-white/[0.03] backdrop-blur p-4 rounded-2xl border border-white/10">
        <Chart options={stackedOptions} series={stackedSeries} type="bar" height={350} />
      </div>
      <div className="bg-white/[0.03] backdrop-blur p-4 rounded-2xl border border-white/10">
        <Chart options={totalDurationOptions} series={totalDurationSeries} type="line" height={350} />
      </div>
      <div className="bg-white/[0.03] backdrop-blur p-4 rounded-2xl border border-white/10">
        <Chart options={avgDurationOptions} series={avgDurationSeries} type="bar" height={350} />
      </div>
    </div>
  );
}