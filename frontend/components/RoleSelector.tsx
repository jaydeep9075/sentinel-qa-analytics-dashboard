"use client";
import { useRB } from "@/lib/RBContext";

export default function RoleSelector() {
  const { roles, selectedRole, setSelectedRole, loading, canSwitchRole } = useRB();

  if (loading) return <div className="text-xs text-gray-500">Loading roles...</div>;
  if (roles.length === 0) return null;

  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    if (canSwitchRole) {
      setSelectedRole(e.target.value);
    }
  };

  return (
    <select
      value={selectedRole || ""}
      onChange={handleChange}
      disabled={!canSwitchRole}
      className={`bg-black/50 border border-white/10 rounded-lg px-3 py-1 text-sm ml-2 ${
        !canSwitchRole ? "opacity-50 cursor-not-allowed" : ""
      }`}
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