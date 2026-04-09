"use client";
import { useIngestion } from "@/lib/IngestionContext";

export default function IngestionSelector() {
  const { ingestions, selectedIngestion, setSelectedIngestion, loading } =
    useIngestion();

  if (loading) return <div className="text-xs text-gray-500">Loading...</div>;
  if (ingestions.length === 0) return null;

  return (
    <select
      value={selectedIngestion || ""}
      onChange={(e) => setSelectedIngestion(e.target.value)}
      className="bg-black/50 border border-white/10 rounded-lg px-3 py-1 text-sm"
    >
      {ingestions.map((ing) => (
        <option key={ing.id} value={ing.id}>
          {ing.id}
        </option>
      ))}
    </select>
  );
}
