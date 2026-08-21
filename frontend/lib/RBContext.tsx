"use client";
import { createContext, useCallback, useContext, useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { usePermissions } from "./usePermissions";
import { ACTIVE_PROJECT_KEY, PROJECT_CHANGED_EVENT, purgeProjectScopedCache } from "./api";

interface RBContextType {
  selectedRole: string | null;
  setSelectedRole: (role: string) => void;
  selectedProject: string | null;
  setSelectedProject: (project: string) => void;
  roles: string[];
  projects: string[];
  refreshProjects: () => Promise<void>;
  loading: boolean;
  userRole: string | null;
  canSwitchRole: boolean;
}

const RBContext = createContext<RBContextType | undefined>(undefined);
const RB_CACHE_KEY = "qa_cache:rb_context:v1";

/**
 * The chat persona - which role the assistant *writes for* - is stored under
 * its own key.
 *
 * It used to share `localStorage.role` with the account role written at
 * login, so picking "QA_Manager" in the dashboard's answer-style dropdown
 * silently rewrote the signed-in account's role: an admin would come back to
 * the header showing them as a QA_Manager, and anything reading that key saw
 * a role the server had never granted. Two different things, two keys.
 */
const ANSWER_STYLE_KEY = "answerStyle";

/**
 * The answer style to start on.
 *
 * The account's own role when it has a persona file in roles/*.md - so an
 * SDET reads SDET-shaped answers without ever opening the dropdown. `admin`
 * has no persona file (an administrator is an account type, not a voice the
 * assistant writes in), so an admin starts on the first available persona
 * and can switch. There is no "unset" state: every session gets a concrete
 * style, because "no style" only ever meant "whatever the model felt like".
 */
function defaultAnswerStyleFor(accountRole: string | null, available: string[]): string | null {
  const normalized = String(accountRole || "").trim().toLowerCase();
  if (normalized && available.includes(normalized)) return normalized;
  return available[0] ?? null;
}

type RBCacheShape = {
  roles: string[];
  projects: string[];
  selectedProject: string | null;
};

function readRBCache(): RBCacheShape | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(RB_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as RBCacheShape;
    if (!Array.isArray(parsed.roles) || !Array.isArray(parsed.projects)) return null;
    return parsed;
  } catch {
    return null;
  }
}

function writeRBCache(payload: RBCacheShape): void {
  if (typeof window === "undefined") return;
  try {
    sessionStorage.setItem(RB_CACHE_KEY, JSON.stringify(payload));
  } catch {
    // Ignore storage errors.
  }
}

function getAuthHeaders(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function RBProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [selectedRole, setSelectedRole] = useState<string | null>(null);
  const [selectedProject, setSelectedProject] = useState<string | null>(null);
  const [roles, setRoles] = useState<string[]>([]);
  const [projects, setProjects] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [storedUserRole, setStoredUserRole] = useState<string | null>(null);
  // /auth/permissions is authoritative for the account role. localStorage is
  // only the instant-on fallback for the first paint, and older builds of
  // this app wrote the chat persona into that same key - so where the two
  // disagree, the server wins.
  const { permissions } = usePermissions();
  const userRole = permissions.role || storedUserRole;

  const fetchData = useCallback(async () => {
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const headers = getAuthHeaders();

    try {
      const [rolesRes, projectsRes] = await Promise.all([
        fetch(`${apiBase}/roles`, { headers }),
        fetch(`${apiBase}/projects`, { headers }),
      ]);

      if (rolesRes.status === 401 || projectsRes.status === 401) {
        // Stale/expired token - same recovery path as the dashboard layout's
        // own auth guard, so the user lands back on /login instead of
        // silently sitting on a dashboard with no roles/projects.
        localStorage.removeItem("token");
        router.replace("/login");
        return;
      }

      if (!rolesRes.ok || !projectsRes.ok) {
        throw new Error("Failed to fetch roles/projects");
      }

      const rolesData = await rolesRes.json();
      const projectsData = await projectsRes.json();

      const availableRoles: string[] = rolesData.roles || [];
      setRoles(availableRoles);
      setProjects(projectsData.projects || []);

      // Resolve the answer style against the personas that actually exist.
      // Done here rather than on mount because roles/*.md is server-side:
      // until this response lands there is no list to pick a default from.
      setSelectedRole((current) => {
        if (current && availableRoles.includes(current)) return current;
        return defaultAnswerStyleFor(localStorage.getItem("role"), availableRoles);
      });

      const savedProject = localStorage.getItem(ACTIVE_PROJECT_KEY);
      let resolvedProject: string | null = null;
      if (savedProject && projectsData.projects?.includes(savedProject)) {
        resolvedProject = savedProject;
        setSelectedProject(savedProject);
      } else if (projectsData.projects?.length > 0) {
        const firstProject = String(projectsData.projects[0]);
        resolvedProject = firstProject;
        setSelectedProject(firstProject);
        localStorage.setItem(ACTIVE_PROJECT_KEY, firstProject);
      } else {
        // Access was revoked, or the project was deleted. Leaving the stale
        // id in storage means every request keeps sending `x-project` for a
        // project the server will now refuse.
        setSelectedProject(null);
        localStorage.removeItem(ACTIVE_PROJECT_KEY);
      }

      writeRBCache({
        roles: rolesData.roles || [],
        projects: projectsData.projects || [],
        selectedProject: resolvedProject,
      });
    } catch (err) {
      console.error("Error fetching roles/projects:", err);
      setRoles([]);
      setProjects([]);
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    // The account role, written at login. Read-only here.
    const storedRole = localStorage.getItem("role");
    setStoredUserRole(storedRole);
    // The answer style: an explicit earlier choice if there is one, else the
    // account's own role - so an SDET reads SDET-shaped answers without ever
    // touching the dropdown, and an admin starts with no persona at all.
    const savedStyle = localStorage.getItem(ANSWER_STYLE_KEY);
    if (savedStyle) {
      setSelectedRole(savedStyle);
    }

    const cached = readRBCache();
    if (cached) {
      setRoles(cached.roles || []);
      setProjects(cached.projects || []);
      if (cached.selectedProject) {
        setSelectedProject(cached.selectedProject);
      }
      setLoading(false);
    }

    fetchData();
  }, [fetchData]);


  const handleSetSelectedRole = (role: string) => {
    setSelectedRole(role);
    // ANSWER_STYLE_KEY, never "role" - see the note on the constant.
    localStorage.setItem(ANSWER_STYLE_KEY, role);
  };

  const handleSetSelectedProject = (project: string) => {
    if (project === selectedProject) return;
    setSelectedProject(project);
    localStorage.setItem(ACTIVE_PROJECT_KEY, project);
    // Everything cached was an answer about the previous project. Keeping any
    // of it is what made a switched-to project still show the old project's
    // builds and charts.
    purgeProjectScopedCache();
    sessionStorage.removeItem(RB_CACHE_KEY);
    window.dispatchEvent(new CustomEvent(PROJECT_CHANGED_EVENT, { detail: project }));
  };

  // Who may answer as somebody else. This is the LLM chat persona (roles/*.md),
  // not the account role — switching it changes how answers are written, not
  // what the account may do. The two wildcard-permission roles get it; a
  // QA_Manager or SDET reads answers written for their own role.
  const canSwitchRole = userRole === "cto" || userRole === "admin";

  return (
    <RBContext.Provider
      value={{
        selectedRole,
        setSelectedRole: handleSetSelectedRole,
        selectedProject,
        setSelectedProject: handleSetSelectedProject,
        roles,
        projects,
        refreshProjects: fetchData,
        loading,
        userRole,
        canSwitchRole,
      }}
    >
      {children}
    </RBContext.Provider>
  );
}

export function useRB() {
  const ctx = useContext(RBContext);
  if (!ctx) throw new Error("useRB must be used within RBProvider");
  return ctx;
}