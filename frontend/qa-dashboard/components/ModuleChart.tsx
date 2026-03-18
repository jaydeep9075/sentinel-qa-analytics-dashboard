"use client";

import { useEffect, useState } from "react";
import { getModules } from "@/lib/api";
import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend } from "recharts";

export default function ModuleChart() {
  const [data, setData] = useState([]);

  useEffect(() => {
    getModules().then((res) => setData(res.data));
  }, []);

  return (
    <div>
      <h2 className="text-xl mb-4">Module Stability</h2>

      <BarChart width={700} height={350} data={data}>
        <XAxis dataKey="module" />
        <YAxis />
        <Tooltip />
        <Legend />
        <Bar dataKey="passed" fill="green" />
        <Bar dataKey="failed" fill="red" />
      </BarChart>
    </div>
  );
}
