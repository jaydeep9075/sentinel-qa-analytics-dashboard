"use client";

import { useEffect, useState } from "react";
import { getTrend } from "@/lib/api";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";

export default function TrendChart() {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getTrend().then((res) => {
      setData(res.data);
      setLoading(false);
    });
  }, []);

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-[#1e1e1e] border border-[#333333] rounded-lg p-4 shadow-2xl backdrop-blur-sm bg-opacity-95">
          <p className="text-white font-semibold mb-3">Build #{label}</p>
          {payload.map((entry: any, index: number) => (
            <div
              key={index}
              className="flex items-center justify-between gap-4 text-sm"
            >
              <div className="flex items-center gap-2">
                <div
                  className="w-3 h-3 rounded-full"
                  style={{ backgroundColor: entry.color }}
                ></div>
                <span className="text-gray-300 capitalize">{entry.name}:</span>
              </div>
              <span className="text-white font-medium">{entry.value}</span>
            </div>
          ))}
        </div>
      );
    }
    return null;
  };

  const CustomLegend = (props: any) => {
    const { payload } = props;
    return (
      <div className="flex justify-center gap-6 mt-4">
        {payload.map((entry: any, index: number) => (
          <div key={index} className="flex items-center gap-2">
            <div
              className="w-3 h-3 rounded-full"
              style={{ backgroundColor: entry.color }}
            ></div>
            <span className="text-gray-400 text-sm capitalize">
              {entry.value}
            </span>
          </div>
        ))}
      </div>
    );
  };

  if (loading) {
    return (
      <div className="h-full">
        <h2 className="text-xl sm:text-2xl font-bold mb-4 text-white flex items-center">
          <span className="w-1.5 h-7 bg-gradient-to-b from-purple-500 to-purple-600 rounded-full mr-3"></span>
          Build Trend
        </h2>
        <div className="w-full h-[350px] bg-gradient-to-br from-[#1a1a1a] to-[#1e1e1e] rounded-xl animate-pulse flex items-center justify-center">
          <div className="text-purple-400">Loading trend data...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl sm:text-2xl font-bold text-white flex items-center">
          <span className="w-1.5 h-7 bg-gradient-to-b from-purple-500 to-purple-600 rounded-full mr-3"></span>
          Build Trend
        </h2>
        <div className="flex items-center gap-2 bg-[#1e1e1e] px-3 py-1.5 rounded-lg border border-[#333333]">
          <div className="w-2 h-2 bg-purple-500 rounded-full animate-pulse"></div>
          <span className="text-xs text-gray-400">Real-time</span>
        </div>
      </div>

      <div className="w-full bg-[#1a1a1a] rounded-xl p-4 border border-[#333333]">
        <div style={{ height: "350px" }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={data}
              margin={{ top: 20, right: 30, left: 20, bottom: 10 }}
            >
              <defs>
                <linearGradient id="passedGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="failedGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#ef4444" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="#333333"
                vertical={false}
              />
              <XAxis
                dataKey="buildOrder"
                stroke="#6b7280"
                tick={{ fill: "#9ca3af", fontSize: 12 }}
                axisLine={{ stroke: "#333333" }}
                tickLine={{ stroke: "#333333" }}
              />
              <YAxis
                stroke="#6b7280"
                tick={{ fill: "#9ca3af", fontSize: 12 }}
                axisLine={{ stroke: "#333333" }}
                tickLine={{ stroke: "#333333" }}
              />
              <Tooltip content={CustomTooltip} />
              <Legend content={CustomLegend} />
              <Line
                type="monotone"
                dataKey="passed"
                stroke="#10b981"
                strokeWidth={3}
                dot={{
                  fill: "#10b981",
                  r: 4,
                  strokeWidth: 2,
                  stroke: "#1a1a1a",
                }}
                activeDot={{ r: 6, stroke: "#10b981", strokeWidth: 2 }}
                fill="url(#passedGradient)"
              />
              <Line
                type="monotone"
                dataKey="failed"
                stroke="#ef4444"
                strokeWidth={3}
                dot={{
                  fill: "#ef4444",
                  r: 4,
                  strokeWidth: 2,
                  stroke: "#1a1a1a",
                }}
                activeDot={{ r: 6, stroke: "#ef4444", strokeWidth: 2 }}
                fill="url(#failedGradient)"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
