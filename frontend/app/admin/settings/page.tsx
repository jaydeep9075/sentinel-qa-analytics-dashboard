"use client";
import { useCallback, useEffect, useState } from "react";
import { Lock, RefreshCw, Save, Wand2 } from "lucide-react";
import PageTransition from "@/components/PageTransition";
import Skeleton from "@/components/Skeleton";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function authHeaders(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

type LLMSettings = {
  provider: string;
  provider_locked: boolean;
  provider_source: string;
  model: string;
  model_locked: boolean;
  model_source: string;
  api_key_set: boolean;
  api_key_locked: boolean;
  api_key_source: string;
  api_key_masked: string;
  api_base: string;
  api_base_locked: boolean;
  api_base_source: string;
  keyless: boolean;
};

const PROVIDERS = ["gemini", "openai", "anthropic", "azure", "mistral", "groq", "cohere", "deepseek", "openrouter", "together_ai", "bedrock", "vertex_ai", "ollama"];

export default function AdminSettingsPage() {
  const [settings, setSettings] = useState<LLMSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; reply?: string; error?: string; model?: string } | null>(null);

  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [apiBase, setApiBase] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const res = await fetch(`${API}/admin/settings/llm`, { headers: authHeaders() });
      if (!res.ok) throw new Error("Failed to load LLM settings");
      const data: LLMSettings = await res.json();
      setSettings(data);
      setProvider(data.provider);
      setModel(data.model);
      setApiBase(data.api_base);
      setApiKey("");
    } catch {
      setError("Could not load LLM settings.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const save = async () => {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const res = await fetch(`${API}/admin/settings/llm`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          provider: settings?.provider_locked ? undefined : provider,
          model: settings?.model_locked ? undefined : model,
          api_base: settings?.api_base_locked ? undefined : apiBase,
          api_key: settings?.api_key_locked || !apiKey ? undefined : apiKey,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Failed to save");
      setNotice("LLM settings saved.");
      await load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to save LLM settings.");
    } finally {
      setSaving(false);
    }
  };

  const testConnection = async () => {
    setTesting(true);
    setTestResult(null);
    setError("");
    try {
      const res = await fetch(`${API}/admin/settings/llm/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          provider: settings?.provider_locked ? undefined : provider,
          model: settings?.model_locked ? undefined : model,
          api_base: settings?.api_base_locked ? undefined : apiBase,
          api_key: settings?.api_key_locked ? undefined : apiKey || undefined,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Test failed");
      setTestResult(data);
    } catch (err: unknown) {
      setTestResult({ success: false, error: err instanceof Error ? err.message : "Test failed" });
    } finally {
      setTesting(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-6 max-w-2xl">
        <div className="space-y-2">
          <Skeleton className="h-6 w-40" />
          <Skeleton className="h-4 w-full max-w-md" />
        </div>
        <div className="rounded-xl border border-slate-200 dark:border-white/[0.08] p-5 space-y-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="space-y-1.5">
              <Skeleton className="h-3 w-24" />
              <Skeleton className="h-10 w-full" />
            </div>
          ))}
        </div>
      </div>
    );
  }
  if (!settings) {
    return <div className="text-red-400 text-sm bg-red-500/[0.08] p-3 rounded-xl border border-red-500/20">{error}</div>;
  }

  const inputCls =
    "w-full rounded-xl border border-slate-300 dark:border-white/[0.08] bg-white dark:bg-black/60 px-4 py-2.5 text-sm text-slate-900 dark:text-white focus:outline-none focus:border-cyan-500/40 focus:ring-1 focus:ring-cyan-500/30 disabled:opacity-50 disabled:cursor-not-allowed";

  return (
    <PageTransition>
    <div className="space-y-6 max-w-2xl">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold">LLM settings</h2>
          <p className="text-sm text-slate-500 dark:text-white/40">
            Provider, model and credential used for chat and chart generation. A field locked by <code>.env</code> can&apos;t be changed here.
          </p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-2 px-4 py-2 rounded-xl border border-slate-300 dark:border-white/10 text-sm hover:border-cyan-500/40"
        >
          <RefreshCw className="w-4 h-4" /> Refresh
        </button>
      </div>

      {error && <div className="text-red-400 text-sm bg-red-500/[0.08] p-3 rounded-xl border border-red-500/20">{error}</div>}
      {notice && <div className="text-emerald-500 text-sm bg-emerald-500/[0.08] p-3 rounded-xl border border-emerald-500/20">{notice}</div>}

      <div className="rounded-xl border border-slate-200 dark:border-white/[0.08] p-5 space-y-4">
        <Field label="Provider" locked={settings.provider_locked} source={settings.provider_source}>
          <select
            className={inputCls}
            value={provider}
            disabled={settings.provider_locked}
            onChange={(e) => setProvider(e.target.value)}
          >
            {PROVIDERS.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </Field>

        <Field label="Model" locked={settings.model_locked} source={settings.model_source}>
          <input
            className={inputCls}
            value={model}
            disabled={settings.model_locked}
            onChange={(e) => setModel(e.target.value)}
            placeholder={`${provider}/model-name`}
          />
        </Field>

        <Field label="API key" locked={settings.api_key_locked} source={settings.api_key_source}>
          <input
            className={inputCls}
            type="password"
            value={apiKey}
            disabled={settings.api_key_locked}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={settings.api_key_set ? settings.api_key_masked : settings.keyless ? "not required for this provider" : "not set"}
          />
        </Field>

        <Field label="API base URL (optional)" locked={settings.api_base_locked} source={settings.api_base_source}>
          <input
            className={inputCls}
            value={apiBase}
            disabled={settings.api_base_locked}
            onChange={(e) => setApiBase(e.target.value)}
            placeholder="https://... (gateway / self-hosted endpoint)"
          />
        </Field>

        <div className="flex flex-wrap gap-3 pt-2">
          <button
            onClick={save}
            disabled={saving}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 text-white text-sm font-semibold disabled:opacity-60"
          >
            <Save className="w-4 h-4" /> {saving ? "Saving…" : "Save"}
          </button>
          <button
            onClick={testConnection}
            disabled={testing}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-slate-300 dark:border-white/10 text-sm font-semibold hover:border-cyan-500/40 disabled:opacity-60"
          >
            <Wand2 className="w-4 h-4" /> {testing ? "Testing…" : "Test connection"}
          </button>
        </div>

        {testResult && (
          <div
            className={`text-sm p-3 rounded-xl border ${
              testResult.success
                ? "text-emerald-500 bg-emerald-500/[0.08] border-emerald-500/20"
                : "text-red-500 bg-red-500/[0.08] border-red-500/20"
            }`}
          >
            {testResult.success ? (
              <>Success — model replied: “{testResult.reply}” ({testResult.model})</>
            ) : (
              <>Failed: {testResult.error}</>
            )}
          </div>
        )}
      </div>
    </div>
    </PageTransition>
  );
}

function Field({
  label,
  locked,
  source,
  children,
}: {
  label: string;
  locked: boolean;
  source: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-1.5">
        <label className="text-xs font-semibold uppercase tracking-widest text-slate-500 dark:text-white/40">{label}</label>
        {locked && (
          <span
            title={`Set via ${source} — edit .env to change this`}
            className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full bg-slate-200 dark:bg-white/10 text-slate-500 dark:text-white/40"
          >
            <Lock className="w-2.5 h-2.5" /> locked by env
          </span>
        )}
      </div>
      {children}
    </div>
  );
}
