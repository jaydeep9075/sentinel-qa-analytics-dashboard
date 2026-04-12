"use client";
import { createContext, useContext, useState, useEffect } from "react";

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

function getAuthHeaders(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function RBProvider({ children }: { children: React.ReactNode }) {
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

    const fetchData = async () => {
      const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const headers = getAuthHeaders();

      try {
        const [rolesRes, projectsRes] = await Promise.all([
          fetch(`${apiBase}/roles`, { headers }),
          fetch(`${apiBase}/projects`, { headers }),
        ]);

        if (!rolesRes.ok || !projectsRes.ok) {
          throw new Error("Failed to fetch roles/projects");
        }

        const rolesData = await rolesRes.json();
        const projectsData = await projectsRes.json();

        setRoles(rolesData.roles || []);
        setProjects(projectsData.projects || []);

        const savedProject = localStorage.getItem("selectedProject");
        if (savedProject && projectsData.projects?.includes(savedProject)) {
          setSelectedProject(savedProject);
        } else if (projectsData.projects?.length > 0) {
          setSelectedProject(projectsData.projects[0]);
        }
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