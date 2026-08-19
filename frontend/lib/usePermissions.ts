"use client";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type Permissions = {
  role: string;
  is_admin: boolean;
  permissions: string[];
  /** Identity, so the header's account menu doesn't need a second request. */
  username: string;
  full_name: string;
  workspace_id: string;
};

const EMPTY: Permissions = {
  role: "",
  is_admin: false,
  permissions: [],
  username: "",
  full_name: "",
  workspace_id: "",
};

// Module-level, keyed by token: every mount of this hook across the app
// (dashboard, IngestionSelector, ...) shares one fetch instead of each
// re-requesting /auth/permissions on its own mount. That's what keeps
// switching pages within a session from re-triggering the loading flash
// this hook is designed to avoid in the first place - see `has()` below.
let cache: { token: string; data: Permissions } | null = null;
let inflight: Promise<Permissions> | null = null;

async function fetchPermissions(token: string): Promise<Permissions> {
  if (cache && cache.token === token) return cache.data;
  if (!inflight) {
    inflight = fetch(`${API}/auth/permissions`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => (r.ok ? r.json() : EMPTY))
      .catch(() => EMPTY)
      // Spread over EMPTY: an older backend that predates the identity
      // fields returns only the three permission keys, and the menu reads
      // `permissions.username` unconditionally.
      .then((data: Partial<Permissions>) => ({ ...EMPTY, ...data }))
      .then((data: Permissions) => {
        cache = { token, data };
        inflight = null;
        return data;
      });
  }
  return inflight;
}

export function usePermissions() {
  const [permissions, setPermissions] = useState<Permissions>(() => {
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
    return token && cache?.token === token ? cache.data : EMPTY;
  });
  const [loaded, setLoaded] = useState(() => {
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
    return Boolean(token && cache?.token === token);
  });

  useEffect(() => {
    let cancelled = false;
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
    if (!token) {
      setLoaded(true);
      return;
    }
    if (cache?.token === token) {
      // Already resolved by a prior mount (or the initializer above) -
      // nothing to await, so skip straight to loaded rather than flashing
      // the optimistic default for one render.
      setPermissions(cache.data);
      setLoaded(true);
      return;
    }
    fetchPermissions(token).then((data) => {
      if (!cancelled) {
        setPermissions(data);
        setLoaded(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // Optimistic while unresolved: an action gated on a permission the caller
  // ends up NOT having is caught server-side regardless (this hook only
  // hides buttons, see the components that consume it) - so showing it for
  // the ~100-200ms a first fetch takes is a smaller cost than the opposite,
  // which is every gated control popping into existence a beat after the
  // rest of the page has already rendered. Once resolved, it's exact.
  const has = (permission: string) => (loaded ? permissions.permissions.includes(permission) : true);

  return { permissions, loaded, has, isAdmin: permissions.is_admin };
}
