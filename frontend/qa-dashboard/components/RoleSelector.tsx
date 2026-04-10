"use client";
import { useRB } from "@/lib/RBContext";

export default function RoleSelector() {
  const { roles, selectedRole, setSelectedRole, loading } = useRB();
  if (loading)
    return <div className="text-xs text-gray-500">Loading roles...</div>;
  if (roles.length === 0) return null;

  return (
    <select
      value={selectedRole || ""}
      onChange={(e) => setSelectedRole(e.target.value)}
      className="bg-black/50 border border-white/10 rounded-lg px-3 py-1 text-sm ml-2"
    >
      <option value="">No Role</option>
      {roles.map((r) => (
        <option key={r} value={r}>
          {r.toUpperCase()}
        </option>
      ))}
    </select>
  );
}
