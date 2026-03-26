"use client";

import { useEffect, useState } from "react";
import { getFailures } from "@/lib/api";

export default function FailuresTable() {
  const [data, setData] = useState<any[]>([]);

  useEffect(() => {
    getFailures().then((res) => setData(res.data));
  }, []);

  return (
    <div>
      <h2 className="text-lg sm:text-xl font-semibold mb-4 text-white flex items-center">
        <span className="w-1 h-6 bg-red-500 rounded-full mr-3"></span>
        Failed Tests
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
                Error
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
                <td className="px-4 py-3 text-sm text-red-400">
                  {t.error_msg}
                </td>
                <td className="px-4 py-3 text-sm text-gray-300">
                  {t.duration_sec}s
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
