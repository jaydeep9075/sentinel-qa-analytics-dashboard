"use client";
import { useRB } from "@/lib/RBContext";
import { Users, ChevronDown } from "lucide-react";

export default function RoleSelector() {
  const { roles, selectedRole, setSelectedRole, loading, canSwitchRole } = useRB();

  if (loading) return <div className="text-[10px] text-white/20 uppercase tracking-widest">Loading roles...</div>;
  if (roles.length === 0) return null;

  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    if (canSwitchRole) {
      setSelectedRole(e.target.value);
    }
  };

  return (
    <div className="relative flex items-center gap-1.5">
      <Users className="w-3.5 h-3.5 text-amber-500/50" />
      <select
        value={selectedRole || ""}
        onChange={handleChange}
        disabled={!canSwitchRole}
        className={`appearance-none bg-white/[0.03] border border-white/[0.08] rounded-lg px-3 py-1.5 pr-8 text-xs text-white/60 hover:border-amber-500/20 focus:outline-none focus:border-amber-500/30 focus:ring-1 focus:ring-amber-500/20 transition-all cursor-pointer ${
          !canSwitchRole ? "opacity-40 cursor-not-allowed" : ""
        }`}
      >
        <option value="" className="bg-black text-white">No Role</option>
        {roles.map((r) => (
          <option key={r} value={r} className="bg-black text-white">
            {r.toUpperCase()}
          </option>
        ))}
      </select>
      <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-white/20 pointer-events-none" />
    </div>
  );
}