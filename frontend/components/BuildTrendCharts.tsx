"use client";

import React from "react";
import dynamic from "next/dynamic";
import type { ApexOptions } from "apexcharts";
import { useTheme } from "@/lib/theme";

const Chart = dynamic(() => import("react-apexcharts"), { ssr: false });

interface Props {
  chartData: {
    buildNumber: number;
    label: string;
    passRate: number;
    passed: number;
    failed: number;
    skipped: number;          // new
    totalDuration: number;
    avgDuration: number;
  }[];
}

export default function BuildTrendCharts({ chartData }: Props) {
  const { isDark } = useTheme();

  if (!chartData || chartData.length === 0) {
    return <div className="p-8 text-center text-red-400/60 text-sm">No chart data</div>;
  }

  const categories = chartData.map(d => d.label);

  // shared theme tokens
  const labelColor = isDark ? "rgba(255,255,255,0.45)" : "rgba(15,23,42,0.65)";
  const gridColor = isDark ? "rgba(255,255,255,0.08)" : "rgba(15,23,42,0.08)";
  const titleStyle = { color: isDark ? "#ffffff" : "#0f172a", fontSize: "14px", fontWeight: "600" as const };

  // 1. Pass Rate Trend
  const passRateOptions: ApexOptions = {
    chart: { type: "line", height: 350, toolbar: { show: false }, background: "transparent" },
    stroke: { curve: "smooth", width: 3 },
    colors: ["#00f0ff"],
    xaxis: { categories, labels: { style: { colors: labelColor } } },
    yaxis: { title: { text: "Pass Rate (%)", style: { color: labelColor } }, min: 0, max: 100, labels: { style: { colors: labelColor } } },
    title: { text: "Pass Rate Trend (executed only)", align: "left", style: titleStyle },
    tooltip: { theme: isDark ? "dark" : "light", y: { formatter: (val: number) => val.toFixed(1) + "%" } },
    grid: { borderColor: gridColor },
  };
  const passRateSeries = [{ name: "Pass Rate", data: chartData.map(d => d.passRate) }];

  // 2. Passed vs Failed vs Skipped (Stacked Bar)
  const stackedOptions: ApexOptions = {
    chart: { type: "bar", height: 350, stacked: true, toolbar: { show: false }, background: "transparent" },
    colors: ["#10b981", "#ef4444", "#6b7280"],
    xaxis: { categories, labels: { style: { colors: labelColor } } },
    yaxis: { title: { text: "Number of Tests", style: { color: labelColor } }, labels: { style: { colors: labelColor } } },
    legend: { position: "top", labels: { colors: isDark ? "#fff" : "#0f172a" } },
    title: { text: "Test Results Breakdown (incl. skipped)", align: "left", style: titleStyle },
    tooltip: { theme: isDark ? "dark" : "light" },
    grid: { borderColor: gridColor },
  };
  const stackedSeries = [
    { name: "Passed", data: chartData.map(d => d.passed) },
    { name: "Failed", data: chartData.map(d => d.failed) },
    { name: "Skipped", data: chartData.map(d => d.skipped) },
  ];

  // 3. Total Duration
  const totalDurationOptions: ApexOptions = {
    chart: { type: "line", height: 350, toolbar: { show: false }, background: "transparent" },
    stroke: { curve: "smooth", width: 3 },
    colors: ["#a855f7"],
    xaxis: { categories, labels: { style: { colors: labelColor } } },
    yaxis: { title: { text: "Total Duration (seconds)", style: { color: labelColor } }, labels: { style: { colors: labelColor } } },
    title: { text: "Total Duration", align: "left", style: titleStyle },
    tooltip: { theme: isDark ? "dark" : "light", y: { formatter: (val: number) => val.toFixed(2) + " s" } },
    grid: { borderColor: gridColor },
  };
  const totalDurationSeries = [{ name: "Total Duration", data: chartData.map(d => d.totalDuration) }];

  // 4. Average Test Duration
  const avgDurationOptions: ApexOptions = {
    chart: { type: "bar", height: 350, toolbar: { show: false }, background: "transparent" },
    colors: ["#f59e0b"],
    xaxis: { categories, labels: { style: { colors: labelColor } } },
    yaxis: { title: { text: "Average Duration (seconds)", style: { color: labelColor } }, labels: { style: { colors: labelColor } } },
    title: { text: "Average Test Duration per Build", align: "left", style: titleStyle },
    tooltip: { theme: isDark ? "dark" : "light", y: { formatter: (val: number) => val.toFixed(2) + " s" } },
    grid: { borderColor: gridColor },
  };
  const avgDurationSeries = [{ name: "Avg Duration", data: chartData.map(d => d.avgDuration) }];

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div className="bg-white border border-slate-200 dark:bg-white/[0.02] dark:border-white/[0.06] backdrop-blur-sm p-5 rounded-2xl hover:border-cyan-500/15 transition-all">
        <Chart options={passRateOptions} series={passRateSeries} type="line" height={350} />
      </div>
      <div className="bg-white border border-slate-200 dark:bg-white/[0.02] dark:border-white/[0.06] backdrop-blur-sm p-5 rounded-2xl hover:border-emerald-500/15 transition-all">
        <Chart options={stackedOptions} series={stackedSeries} type="bar" height={350} />
      </div>
      <div className="bg-white border border-slate-200 dark:bg-white/[0.02] dark:border-white/[0.06] backdrop-blur-sm p-5 rounded-2xl hover:border-purple-500/15 transition-all">
        <Chart options={totalDurationOptions} series={totalDurationSeries} type="line" height={350} />
      </div>
      <div className="bg-white border border-slate-200 dark:bg-white/[0.02] dark:border-white/[0.06] backdrop-blur-sm p-5 rounded-2xl hover:border-amber-500/15 transition-all">
        <Chart options={avgDurationOptions} series={avgDurationSeries} type="bar" height={350} />
      </div>
    </div>
  );
}