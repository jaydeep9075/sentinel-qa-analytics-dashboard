"use client";
import { useState } from "react";
import { useIngestion } from "@/lib/IngestionContext";
import { Database, ChevronDown, Trash2 } from "lucide-react";

export default function IngestionSelector() {
  const { ingestions, selectedIngestion, setSelectedIngestion, loading, refreshIngestions } =
    useIngestion();
  const [showDeleteMenu, setShowDeleteMenu] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  if (loading) return <div className="text-[10px] text-slate-500 dark:text-white/20 uppercase tracking-widest">Loading...</div>;
  if (ingestions.length === 0) return null;

  const handleDelete = async (ingestionId: string) => {
    setIsDeleting(true);
    try {
      const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const token = localStorage.getItem("token");
      const res = await fetch(`${API_BASE}/ingestions/${ingestionId}`, {
        method: "DELETE",
        headers: {
          "Content-Type": "application/json",
          ...(token && { "Authorization": `Bearer ${token}` }),
        },
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || "Failed to delete ingestion");
      }
      if (selectedIngestion === ingestionId) {
        setSelectedIngestion(ingestions.find(i => i.id !== ingestionId)?.id || "");
      }
      await refreshIngestions();
      setDeleteConfirm(null);
      setShowDeleteMenu(false);
    } catch (error) {
      console.error("Delete failed:", error);
      alert("Failed to delete ingestion");
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div className="relative flex items-center gap-1.5">
      <Database className="w-3.5 h-3.5 text-cyan-500/50" />
      <select
        value={selectedIngestion || ""}
        onChange={(e) => {
          setSelectedIngestion(e.target.value);
          setShowDeleteMenu(false);
        }}
        className="appearance-none bg-white border border-slate-300 rounded-lg px-3 py-1.5 pr-8 text-xs text-slate-700 hover:border-cyan-500/30 focus:outline-none focus:border-cyan-500/40 focus:ring-1 focus:ring-cyan-500/20 transition-all cursor-pointer dark:bg-white/[0.03] dark:border-white/[0.08] dark:text-white/60 dark:hover:border-cyan-500/20 dark:focus:border-cyan-500/30"
      >
        {ingestions.map((ing) => (
          <option key={ing.id} value={ing.id} className="bg-white text-slate-700 dark:bg-black dark:text-white">
            {ing.build_label}
          </option>
        ))}
      </select>
      <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-slate-400 dark:text-white/20 pointer-events-none" />

      {/* Delete button */}
      <div className="relative">
        <button
          onClick={() => setShowDeleteMenu(!showDeleteMenu)}
          className="p-1.5 rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-100/20 dark:text-white/40 dark:hover:text-red-400 dark:hover:bg-red-500/10 transition-all"
          title="Delete this build"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>

        {showDeleteMenu && (
          <div className="absolute right-0 mt-2 z-50 w-48 rounded-lg border border-red-200 bg-white p-3 shadow-[0_10px_35px_rgba(15,23,42,0.12)] dark:border-red-500/20 dark:bg-black/95">
            <p className="text-xs text-slate-700 dark:text-white/70 mb-3">Delete this build? This cannot be undone.</p>
            <div className="flex gap-2">
              <button
                onClick={() => setShowDeleteMenu(false)}
                className="flex-1 rounded-lg px-3 py-1.5 text-xs font-semibold border border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-white/[0.12] dark:text-white/70 dark:hover:bg-white/[0.07] transition-all"
              >
                Cancel
              </button>
              <button
                onClick={() => setDeleteConfirm(selectedIngestion)}
                disabled={isDeleting}
                className="flex-1 rounded-lg px-3 py-1.5 text-xs font-semibold text-white bg-red-600 hover:bg-red-700 disabled:opacity-60 disabled:cursor-not-allowed transition-all"
              >
                {isDeleting ? "Deleting..." : "Delete"}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Confirmation modal */}
      {deleteConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-black/95 rounded-xl border border-slate-200 dark:border-white/[0.08] p-6 max-w-sm shadow-[0_20px_50px_rgba(15,23,42,0.3)]">
            <h3 className="text-base font-semibold text-slate-900 dark:text-white mb-2">Confirm Delete</h3>
            <p className="text-sm text-slate-600 dark:text-white/60 mb-4">
              Are you sure you want to delete this build and all its related data? This action cannot be undone.
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setDeleteConfirm(null)}
                disabled={isDeleting}
                className="flex-1 rounded-lg px-4 py-2 text-sm font-semibold border border-slate-300 text-slate-700 hover:bg-slate-100 disabled:opacity-60 dark:border-white/[0.12] dark:text-white/70 dark:hover:bg-white/[0.07]"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDelete(deleteConfirm)}
                disabled={isDeleting}
                className="flex-1 rounded-lg px-4 py-2 text-sm font-semibold text-white bg-red-600 hover:bg-red-700 disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {isDeleting ? "Deleting..." : "Yes, Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
