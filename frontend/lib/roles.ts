// lib/roles.ts
//
// The account roles an admin can assign, and the one way they are spelled in
// the UI. Mirrors services/permissions.py KNOWN_ROLES — the backend rejects
// anything outside that list, so keeping a second, drifting copy in a page
// component was how a role could appear in a dropdown and then 400 on save.

/** Assignable account roles, in the order they should appear in a dropdown. */
export const ASSIGNABLE_ROLES = ["admin", "cto", "qa-manager", "sdet"] as const;

/** Retired roles: still held by older accounts, never offered for assignment.
 *  Mirrors services/permissions.py LEGACY_ROLES. */
export const LEGACY_ROLES = ["qa-engineer", "developer", "viewer"] as const;

/** Words that are acronyms, not names, and stay fully capitalised. */
const ACRONYMS = new Set(["qa", "cto", "sdet", "ui", "api"]);

/**
 * "qa-manager" -> "QA_Manager", "sdet" -> "SDET", "admin" -> "Admin".
 * Underscore-joined on purpose: these read as role identifiers in the admin
 * console, not as prose.
 */
export function formatRoleLabel(role: string): string {
  const normalized = String(role || "").trim().toLowerCase();
  if (!normalized) return "";
  return normalized
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map((part) =>
      ACRONYMS.has(part) ? part.toUpperCase() : `${part[0].toUpperCase()}${part.slice(1)}`,
    )
    .join("_");
}

/** True when an account still carries a role that is no longer assignable.
 *  The role keeps working (services/permissions.py resolves LEGACY_ROLES),
 *  but it must not appear as something an admin can pick — offering "Viewer"
 *  in the dropdown is offering to create more of them. The row shows a
 *  placeholder instead, so the admin can see it needs reassigning. */
export function isRetiredRole(role?: string | null): boolean {
  const normalized = String(role || "").trim().toLowerCase();
  return Boolean(normalized) && !ASSIGNABLE_ROLES.includes(normalized as typeof ASSIGNABLE_ROLES[number]);
}
