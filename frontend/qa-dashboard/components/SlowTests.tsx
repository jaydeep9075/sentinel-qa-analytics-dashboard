"use client";

import { useEffect, useState } from "react";
import { getSlowTests } from "@/lib/api";

export default function SlowTests() {
  const [data, setData] = useState<any[]>([]);

  useEffect(() => {
    getSlowTests().then((res) => setData(res.data));
  }, []);

  return (
    <div>
      <h2 className="text-lg sm:text-xl font-semibold mb-4 text-white flex items-center">
        <span className="w-1 h-6 bg-yellow-500 rounded-full mr-3"></span>
        Slowest Tests
      </h2>

      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-[#2a2a2a]">
          <thead>
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                Name
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                Module
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                Duration
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#2a2a2a]">
            {data.map((t, i) => (
              <tr key={i} className="hover:bg-[#0f0f0f] transition-colors">
                <td className="px-4 py-3 text-sm text-gray-300">{t.name}</td>
                <td className="px-4 py-3 text-sm text-gray-300">{t.module}</td>
                <td className="px-4 py-3 text-sm">
                  <span className="inline-flex items-center px-2 py-1 rounded-lg bg-yellow-500/10 text-yellow-400">
                    ⏱️ {t.duration_sec}s
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
