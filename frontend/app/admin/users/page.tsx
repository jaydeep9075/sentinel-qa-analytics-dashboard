"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, KeyRound, RefreshCw, ShieldAlert, Trash2, UserPlus, X } from "lucide-react";
import PageTransition from "@/components/PageTransition";
import { SkeletonRows } from "@/components/Skeleton";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const ROLES = ["admin", "cto", "qa-manager", "qa-engineer", "developer", "viewer"];

type User = {
  username: string;
  role: string;
  workspace_id: string;
  email: string;
  full_name: string;
  status: "pending" | "active" | "disabled";
  requested_workspace: string;
  must_change_password: boolean;
  token_limit: number;
  created_at: string;
  last_login_at: string;
};

function authHeaders(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

const STATUS_STYLES: Record<string, string> = {
  pending: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/25",
  active: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/25",
  disabled: "bg-slate-500/10 text-slate-500 dark:text-white/40 border-slate-500/25",
};

export default function AdminUsersPage() {
  const router = useRouter();
  const [users, setUsers] = useState<User[]>([]);
  const [workspaces, setWorkspaces] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [ownUsername, setOwnUsername] = useState("");

  useEffect(() => {
    setOwnUsername((localStorage.getItem("username") || "").toLowerCase());
  }, []);

  const load = useCallback(async () => {
    setError("");
    try {
      const res = await fetch(`${API}/admin/users`, { headers: authHeaders() });
      if (res.status === 401) {
        router.push("/login");
        return;
      }
      if (res.status === 403) {
        setError("You need administrator privileges to manage users.");
        setUsers([]);
        return;
      }
      const data = await res.json();
      setUsers(data.users || []);
      setWorkspaces(data.workspaces || []);
    } catch {
      setError("Could not reach the backend.");
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    load();
  }, [load]);

  const call = async (url: string, init: RequestInit, successMessage: string) => {
    setError("");
    setNotice("");
    try {
      const res = await fetch(url, {
        ...init,
        headers: { "Content-Type": "application/json", ...authHeaders(), ...(init.headers || {}) },
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Request failed");
      setNotice(successMessage);
      await load();
      return true;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Request failed");
      return false;
    }
  };

  const patch = (username: string, body: Record<string, unknown>, msg: string) =>
    call(`${API}/admin/users/${encodeURIComponent(username)}`, { method: "PATCH", body: JSON.stringify(body) }, msg);

  const pending = useMemo(() => users.filter((u) => u.status === "pending"), [users]);
  const rest = useMemo(() => users.filter((u) => u.status !== "pending"), [users]);

  return (
    <PageTransition>
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h2 className="text-xl font-bold">User management</h2>
          <p className="text-sm text-slate-500 dark:text-white/40">
            Approve access requests, assign roles and workspaces, and set per-account token limits.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={load}
            className="flex items-center gap-2 px-4 py-2 rounded-xl border border-slate-300 dark:border-white/10 text-sm hover:border-cyan-500/40"
          >
            <RefreshCw className="w-4 h-4" /> Refresh
          </button>
          <button
            onClick={() => setShowCreate((v) => !v)}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 text-white text-sm font-semibold"
          >
            <UserPlus className="w-4 h-4" /> New user
          </button>
        </div>
      </div>

      {error && (
        <div className="text-red-400 text-sm bg-red-500/[0.08] p-3 rounded-xl border border-red-500/20">{error}</div>
      )}
      {notice && (
        <div className="text-emerald-500 text-sm bg-emerald-500/[0.08] p-3 rounded-xl border border-emerald-500/20">
          {notice}
        </div>
      )}

      {showCreate && (
        <CreateUserForm
          workspaces={workspaces}
          onCancel={() => setShowCreate(false)}
          onSubmit={async (body) => {
            const ok = await call(`${API}/admin/users`, { method: "POST", body: JSON.stringify(body) }, `Created ${body.username}.`);
            if (ok) setShowCreate(false);
          }}
        />
      )}

      {loading && <SkeletonRows count={4} />}

      {pending.length > 0 && (
        <section className="space-y-3">
          <h3 className="text-sm font-semibold uppercase tracking-widest text-amber-500">
            Awaiting approval ({pending.length})
          </h3>
          <div className="space-y-2">
            {pending.map((u) => (
              <PendingRow key={u.username} user={u} workspaces={workspaces} onApprove={patch} onReject={patch} />
            ))}
          </div>
        </section>
      )}

      <section className="space-y-3">
        <h3 className="text-sm font-semibold uppercase tracking-widest text-slate-500 dark:text-white/40">
          Accounts ({rest.length})
        </h3>
        <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-white/[0.08]">
          <table className="w-full text-sm min-w-[920px]">
            <thead className="bg-slate-50 dark:bg-white/[0.03] text-left">
              <tr className="text-xs uppercase tracking-wider text-slate-500 dark:text-white/40">
                <th className="px-4 py-3">User</th>
                <th className="px-4 py-3">Role</th>
                <th className="px-4 py-3">Workspace</th>
                <th className="px-4 py-3">Token limit</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rest.map((u) => (
                <UserRow key={u.username} user={u} workspaces={workspaces} isSelf={u.username === ownUsername} onPatch={patch} onCall={call} />
              ))}
              {!loading && rest.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-slate-400 dark:text-white/30">
                    No accounts yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
    </PageTransition>
  );
}

function PendingRow({
  user,
  workspaces,
  onApprove,
  onReject,
}: {
  user: User;
  workspaces: string[];
  onApprove: (u: string, b: Record<string, unknown>, m: string) => Promise<boolean>;
  onReject: (u: string, b: Record<string, unknown>, m: string) => Promise<boolean>;
}) {
  const [workspace, setWorkspace] = useState(user.requested_workspace || workspaces[0] || "default");
  const [role, setRole] = useState("qa-engineer");

  return (
    <div className="flex flex-wrap items-center gap-3 p-4 rounded-xl border border-amber-500/25 bg-amber-500/[0.04]">
      <div className="flex-1 min-w-[180px]">
        <p className="font-semibold">{user.username}</p>
        <p className="text-xs text-slate-500 dark:text-white/40">
          {user.email || "no email"}
          {user.requested_workspace && ` · requested "${user.requested_workspace}"`}
        </p>
      </div>
      <input
        list="workspace-options"
        value={workspace}
        onChange={(e) => setWorkspace(e.target.value)}
        placeholder="workspace"
        className="px-3 py-2 rounded-lg bg-white dark:bg-black/50 border border-slate-300 dark:border-white/10 text-sm w-40"
      />
      <select
        value={role}
        onChange={(e) => setRole(e.target.value)}
        className="px-3 py-2 rounded-lg bg-white dark:bg-black/50 border border-slate-300 dark:border-white/10 text-sm"
      >
        {ROLES.map((r) => (
          <option key={r} value={r}>
            {r}
          </option>
        ))}
      </select>
      <button
        onClick={() => onApprove(user.username, { status: "active", workspace_id: workspace, role }, `Approved ${user.username}.`)}
        className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-emerald-500 text-white text-sm font-medium"
      >
        <Check className="w-4 h-4" /> Approve
      </button>
      <button
        onClick={() => onReject(user.username, { status: "disabled" }, `Rejected ${user.username}.`)}
        className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-300 dark:border-white/10 text-sm"
      >
        <X className="w-4 h-4" /> Reject
      </button>
      <datalist id="workspace-options">
        {workspaces.map((w) => (
          <option key={w} value={w} />
        ))}
      </datalist>
    </div>
  );
}

function UserRow({
  user,
  workspaces,
  isSelf,
  onPatch,
  onCall,
}: {
  user: User;
  workspaces: string[];
  isSelf: boolean;
  onPatch: (u: string, b: Record<string, unknown>, m: string) => Promise<boolean>;
  onCall: (url: string, init: RequestInit, msg: string) => Promise<boolean>;
}) {
  const [workspace, setWorkspace] = useState(user.workspace_id);
  const [tokenLimit, setTokenLimit] = useState(String(user.token_limit || 0));

  useEffect(() => setWorkspace(user.workspace_id), [user.workspace_id]);
  useEffect(() => setTokenLimit(String(user.token_limit || 0)), [user.token_limit]);

  const resetPassword = async () => {
    const password = window.prompt(`New password for ${user.username} (min 8 characters):`);
    if (!password) return;
    const forceChange = window.confirm(
      "Force this user to change it on next login? OK = yes (recommended), Cancel = no."
    );
    await onCall(
      `${API}/admin/users/${encodeURIComponent(user.username)}/password`,
      { method: "POST", body: JSON.stringify({ password, force_change: forceChange }) },
      `Password reset for ${user.username}.`
    );
  };

  const remove = async () => {
    if (!window.confirm(`Permanently delete ${user.username}? This cannot be undone.`)) return;
    await onCall(
      `${API}/admin/users/${encodeURIComponent(user.username)}`,
      { method: "DELETE" },
      `Deleted ${user.username}.`
    );
  };

  return (
    <tr className="border-t border-slate-200 dark:border-white/[0.06]">
      <td className="px-4 py-3">
        <div className="flex items-center gap-1.5">
          <p className="font-medium">{user.username}</p>
          {user.must_change_password && (
            <span title="Must change password on next login">
              <ShieldAlert className="w-3.5 h-3.5 text-amber-500" />
            </span>
          )}
        </div>
        <p className="text-xs text-slate-400 dark:text-white/30">{user.email || "—"}</p>
      </td>
      <td className="px-4 py-3">
        <select
          value={user.role || "viewer"}
          disabled={isSelf}
          title={isSelf ? "Use another admin account to change your own role" : undefined}
          onChange={(e) => onPatch(user.username, { role: e.target.value }, `Updated ${user.username}.`)}
          className="px-2 py-1.5 rounded-lg bg-white dark:bg-black/50 border border-slate-300 dark:border-white/10 text-sm disabled:opacity-50"
        >
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
      </td>
      <td className="px-4 py-3">
        <input
          list="workspace-options"
          value={workspace}
          onChange={(e) => setWorkspace(e.target.value)}
          onBlur={() => {
            if (workspace !== user.workspace_id) {
              onPatch(user.username, { workspace_id: workspace }, `Moved ${user.username} to "${workspace}".`);
            }
          }}
          className="px-2 py-1.5 rounded-lg bg-white dark:bg-black/50 border border-slate-300 dark:border-white/10 text-sm w-32"
        />
        <datalist id="workspace-options">
          {workspaces.map((w) => (
            <option key={w} value={w} />
          ))}
        </datalist>
      </td>
      <td className="px-4 py-3">
        <input
          type="number"
          min={0}
          value={tokenLimit}
          onChange={(e) => setTokenLimit(e.target.value)}
          onBlur={() => {
            const parsed = Math.max(0, parseInt(tokenLimit, 10) || 0);
            if (parsed !== (user.token_limit || 0)) {
              onPatch(
                user.username,
                { token_limit: parsed },
                `Set ${user.username}'s token limit to ${parsed === 0 ? "unlimited" : parsed.toLocaleString()}.`
              );
            }
          }}
          title="0 = unlimited"
          className="px-2 py-1.5 rounded-lg bg-white dark:bg-black/50 border border-slate-300 dark:border-white/10 text-sm w-24"
        />
      </td>
      <td className="px-4 py-3">
        <button
          onClick={() =>
            onPatch(
              user.username,
              { status: user.status === "active" ? "disabled" : "active" },
              `${user.username} is now ${user.status === "active" ? "disabled" : "active"}.`
            )
          }
          className={`px-2.5 py-1 rounded-full border text-xs font-medium ${STATUS_STYLES[user.status]}`}
          title="Click to toggle"
        >
          {user.status}
        </button>
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center justify-end gap-2">
          <button
            onClick={resetPassword}
            title="Reset password"
            className="p-2 rounded-lg border border-slate-300 dark:border-white/10 hover:border-cyan-500/40"
          >
            <KeyRound className="w-4 h-4" />
          </button>
          <button
            onClick={remove}
            title={isSelf ? "You cannot delete your own account" : "Delete user"}
            disabled={isSelf}
            className="p-2 rounded-lg border border-slate-300 dark:border-white/10 hover:border-red-500/40 hover:text-red-500 disabled:opacity-40 disabled:hover:border-slate-300 disabled:hover:text-inherit"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </td>
    </tr>
  );
}

function CreateUserForm({
  workspaces,
  onCancel,
  onSubmit,
}: {
  workspaces: string[];
  onCancel: () => void;
  onSubmit: (body: Record<string, unknown>) => void;
}) {
  const [form, setForm] = useState({
    username: "",
    password: "",
    email: "",
    full_name: "",
    role: "qa-engineer",
    workspace_id: workspaces[0] || "default",
    token_limit: "",
    must_change_password: true,
  });

  const set = (k: string, v: string | boolean) => setForm((f) => ({ ...f, [k]: v }));
  const input =
    "px-3 py-2 rounded-lg bg-white dark:bg-black/50 border border-slate-300 dark:border-white/10 text-sm w-full";

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          ...form,
          token_limit: form.token_limit ? Math.max(0, parseInt(form.token_limit, 10) || 0) : undefined,
        });
      }}
      className="grid gap-3 md:grid-cols-4 items-end p-4 rounded-xl border border-slate-200 dark:border-white/[0.08] bg-slate-50 dark:bg-white/[0.02]"
    >
      <label className="block">
        <span className="text-xs text-slate-500 dark:text-white/40">Username</span>
        <input className={input} value={form.username} onChange={(e) => set("username", e.target.value)} required />
      </label>
      <label className="block">
        <span className="text-xs text-slate-500 dark:text-white/40">Password</span>
        <input
          className={input}
          type="password"
          minLength={8}
          value={form.password}
          onChange={(e) => set("password", e.target.value)}
          required
        />
      </label>
      <label className="block">
        <span className="text-xs text-slate-500 dark:text-white/40">Full name</span>
        <input className={input} value={form.full_name} onChange={(e) => set("full_name", e.target.value)} />
      </label>
      <label className="block">
        <span className="text-xs text-slate-500 dark:text-white/40">Email</span>
        <input className={input} type="email" value={form.email} onChange={(e) => set("email", e.target.value)} />
      </label>
      <label className="block">
        <span className="text-xs text-slate-500 dark:text-white/40">Role</span>
        <select className={input} value={form.role} onChange={(e) => set("role", e.target.value)}>
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
      </label>
      <label className="block">
        <span className="text-xs text-slate-500 dark:text-white/40">Workspace</span>
        <input
          className={input}
          list="workspace-options"
          value={form.workspace_id}
          onChange={(e) => set("workspace_id", e.target.value)}
          required
        />
      </label>
      <label className="block">
        <span className="text-xs text-slate-500 dark:text-white/40">Token limit (0 = unlimited)</span>
        <input
          className={input}
          type="number"
          min={0}
          placeholder="unlimited"
          value={form.token_limit}
          onChange={(e) => set("token_limit", e.target.value)}
        />
      </label>
      <label className="flex items-center gap-2 pb-2">
        <input
          type="checkbox"
          checked={form.must_change_password}
          onChange={(e) => set("must_change_password", e.target.checked)}
          className="rounded border-slate-300 dark:border-white/20"
        />
        <span className="text-xs text-slate-500 dark:text-white/40">Force password change on first login</span>
      </label>
      <div className="flex gap-2">
        <button type="submit" className="flex-1 px-3 py-2 rounded-lg bg-cyan-500 text-white text-sm font-semibold">
          Create
        </button>
        <button type="button" onClick={onCancel} className="px-3 py-2 rounded-lg border border-slate-300 dark:border-white/10 text-sm">
          Cancel
        </button>
      </div>
      <datalist id="workspace-options">
        {workspaces.map((w) => (
          <option key={w} value={w} />
        ))}
      </datalist>
    </form>
  );
}
