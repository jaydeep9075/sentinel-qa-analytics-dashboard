"use client";
import { createContext, useContext, useState, useEffect } from "react";
import { useRouter } from "next/navigation";

interface RBContextType {
  selectedRole: string | null;
  setSelectedRole: (role: string) => void;
  selectedProject: string | null;
  setSelectedProject: (project: string) => void;
  roles: string[];
  projects: string[];
  loading: boolean;
  userRole: string | null;
  canSwitchRole: boolean;
}

const RBContext = createContext<RBContextType | undefined>(undefined);
const RB_CACHE_KEY = "qa_cache:rb_context:v1";

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
  const [userRole, setUserRole] = useState<string | null>(null);

  useEffect(() => {
    // Get the actual logged‑in user’s role from localStorage (set during login)
    const storedRole = localStorage.getItem("role");
    setUserRole(storedRole);
    // Initial selected role = user’s own role
    if (storedRole) {
      setSelectedRole(storedRole);
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

    const fetchData = async () => {
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

        setRoles(rolesData.roles || []);
        setProjects(projectsData.projects || []);

        const savedProject = localStorage.getItem("selectedProject");
        let resolvedProject: string | null = null;
        if (savedProject && projectsData.projects?.includes(savedProject)) {
          resolvedProject = savedProject;
          setSelectedProject(savedProject);
        } else if (projectsData.projects?.length > 0) {
          resolvedProject = projectsData.projects[0];
          setSelectedProject(resolvedProject);
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
    };

    fetchData();
  }, []);

  const handleSetSelectedRole = (role: string) => {
    setSelectedRole(role);
    localStorage.setItem("role", role);
  };

  const handleSetSelectedProject = (project: string) => {
    setSelectedProject(project);
    localStorage.setItem("selectedProject", project);
  };

  // Only CTO can switch roles
  const canSwitchRole = userRole === "cto";

  return (
    <RBContext.Provider
      value={{
        selectedRole,
        setSelectedRole: handleSetSelectedRole,
        selectedProject,
        setSelectedProject: handleSetSelectedProject,
        roles,
        projects,
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