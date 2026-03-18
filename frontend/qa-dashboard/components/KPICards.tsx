"use client";

import { useEffect, useState } from "react";
import { getKPIs } from "@/lib/api";

export default function KPICards() {
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    getKPIs().then((res) => setData(res.data));
  }, []);

  if (!data) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <div
            key={i}
            className="h-24 bg-[#1a1a1a] rounded-xl animate-pulse"
          ></div>
        ))}
      </div>
    );
  }

  const cards = [
    { label: "Total Tests", value: data.total, icon: "📊", color: "blue" },
    { label: "Passed", value: data.passed, icon: "✅", color: "green" },
    { label: "Failed", value: data.failed, icon: "❌", color: "red" },
    {
      label: "Avg Duration",
      value: `${data.avg_duration}s`,
      icon: "⏱️",
      color: "purple",
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map((card, i) => (
        <div
          key={i}
          className="group relative bg-gradient-to-br from-[#1a1a1a] to-[#0f0f0f] rounded-xl p-6 border border-[#2a2a2a] hover:border-blue-500/50 transition-all hover:shadow-xl hover:shadow-blue-500/5"
        >
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-400 mb-1">{card.label}</p>
              <p className="text-2xl sm:text-3xl font-bold text-white">
                {card.value}
              </p>
            </div>
            <div className="text-3xl opacity-50 group-hover:opacity-100 transition-opacity">
              {card.icon}
            </div>
          </div>
          <div
            className={`absolute bottom-0 left-0 h-1 bg-${card.color}-500 rounded-full w-0 group-hover:w-full transition-all duration-500`}
          ></div>
        </div>
      ))}
    </div>
  );
}
