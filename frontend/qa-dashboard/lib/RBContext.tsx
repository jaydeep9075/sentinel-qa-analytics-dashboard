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
}

const RBContext = createContext<RBContextType | undefined>(undefined);

export function RBProvider({ children }: { children: React.ReactNode }) {
  const [selectedRole, setSelectedRole] = useState<string | null>(null);
  const [selectedProject, setSelectedProject] = useState<string | null>(null);
  const [roles, setRoles] = useState<string[]>([]);
  const [projects, setProjects] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch(`${process.env.NEXT_PUBLIC_API_URL}/roles`).then((r) => r.json()),
      fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects`).then((r) =>
        r.json(),
      ),
    ])
      .then(([rolesData, projectsData]) => {
        setRoles(rolesData.roles || []);
        setProjects(projectsData.projects || []);
        setLoading(false);
      })
      .catch(console.error);
  }, []);

  return (
    <RBContext.Provider
      value={{
        selectedRole,
        setSelectedRole,
        selectedProject,
        setSelectedProject,
        roles,
        projects,
        loading,
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
