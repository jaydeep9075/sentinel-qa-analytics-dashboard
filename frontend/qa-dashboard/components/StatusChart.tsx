"use client";

import { useEffect, useState } from "react";
import { getStatus } from "@/lib/api";
import { BarChart, Bar, XAxis, YAxis, Tooltip } from "recharts";

export default function StatusChart() {
  const [data, setData] = useState<any[]>([]);

  useEffect(() => {
    getStatus().then((res) => {
      const formatted = Object.entries(res.data).map(([k, v]) => ({
        status: k,
        count: v,
      }));

      setData(formatted);
    });
  }, []);

  return (
    <div>
      <h2 className="text-xl mb-4">Status Distribution</h2>

      <BarChart width={400} height={300} data={data}>
        <XAxis dataKey="status" />
        <YAxis />
        <Tooltip />
        <Bar dataKey="count" fill="#8884d8" />
      </BarChart>
    </div>
  );
}
