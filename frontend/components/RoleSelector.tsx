"use client";
import { useRB } from "@/lib/RBContext";
import { Users, ChevronDown } from "lucide-react";
import { formatRoleLabel } from "@/lib/roles";

export default function RoleSelector() {
  const { roles, selectedRole, setSelectedRole, loading, canSwitchRole } = useRB();

  if (loading) return null;
  if (roles.length === 0) return null;
  // Only the wildcard roles may switch persona (see RBContext.canSwitchRole).
  // For everyone else this used to render at 40% opacity and inert — a
  // permanently disabled dropdown teaches nothing and costs the header
  // ~110px. Their role is shown in the account menu instead, where it is
  // information rather than a broken control.
  if (!canSwitchRole) return null;

  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setSelectedRole(e.target.value);
  };

  return (
    <div className="relative flex items-center gap-1.5">
      <Users className="w-3.5 h-3.5 text-amber-500/50" />
      <select
        value={selectedRole || ""}
        onChange={handleChange}
        title="Answer style: which role the chat and chart suggestions are written for"
        className="appearance-none bg-white border border-slate-300 rounded-lg px-3 py-1.5 pr-8 text-xs text-slate-700 hover:border-amber-500/30 focus:outline-none focus:border-amber-500/40 focus:ring-1 focus:ring-amber-500/20 transition-all cursor-pointer dark:bg-white/[0.03] dark:border-white/[0.08] dark:text-white/60 dark:hover:border-amber-500/20 dark:focus:border-amber-500/30"
      >
        {roles.map((r) => (
          <option key={r} value={r} className="bg-white text-slate-700 dark:bg-black dark:text-white">
            {formatRoleLabel(r)}
          </option>
        ))}
      </select>
      <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-slate-400 dark:text-white/20 pointer-events-none" />
    </div>
  );
}