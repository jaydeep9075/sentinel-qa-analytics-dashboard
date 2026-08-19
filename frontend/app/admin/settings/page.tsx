"use client";
import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, KeyRound, RefreshCw, Save, Wand2 } from "lucide-react";
import PageTransition from "@/components/PageTransition";
import Skeleton from "@/components/Skeleton";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function authHeaders(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

type LLMSettings = {
  provider: string;
  provider_source: string;
  model: string;
  model_source: string;
  api_key_set: boolean;
  api_key_source: string;
  api_key_masked: string;
  api_base: string;
  api_base_source: string;
  keyless: boolean;
};

const PROVIDERS = ["gemini", "openai", "anthropic", "azure", "mistral", "groq", "cohere", "deepseek", "openrouter", "together_ai", "bedrock", "vertex_ai", "ollama"];

type SecretKeyInfo = {
  source: string;
  masked: string;
};

type EmbeddingSettings = {
  model: string;
  source: string;
};

// All free, local (sentence-transformers) models - no API cost, work no
// matter which chat LLM provider is configured (including Anthropic, which
// has no embeddings API of its own).
const EMBEDDING_MODELS = [
  "BAAI/bge-small-en-v1.5",        // default: best quality/speed balance
  "all-MiniLM-L6-v2",              // lightest/fastest, lower quality
  "BAAI/bge-base-en-v1.5",         // higher quality, slower, larger
  "all-mpnet-base-v2",
  "paraphrase-multilingual-MiniLM-L12-v2", // non-English content
];

function formatProviderLabel(provider: string): string {
  return provider.replace(/_/g, " ").toUpperCase();
}

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

  const [secretKeyInfo, setSecretKeyInfo] = useState<SecretKeyInfo | null>(null);
  const [secretKeyValue, setSecretKeyValue] = useState("");
  const [confirmingRotate, setConfirmingRotate] = useState<"custom" | "generate" | null>(null);
  const [rotating, setRotating] = useState(false);
  const [secretKeyError, setSecretKeyError] = useState("");
  const [secretKeyNotice, setSecretKeyNotice] = useState("");

  const [embeddingSettings, setEmbeddingSettings] = useState<EmbeddingSettings | null>(null);
  const [embeddingModel, setEmbeddingModel] = useState("");
  const [embeddingSaving, setEmbeddingSaving] = useState(false);
  const [embeddingError, setEmbeddingError] = useState("");
  const [embeddingNotice, setEmbeddingNotice] = useState("");

  const loadEmbedding = useCallback(async () => {
    try {
      const res = await fetch(`${API}/admin/settings/embedding`, { headers: authHeaders() });
      if (!res.ok) throw new Error("Failed to load");
      const data: EmbeddingSettings = await res.json();
      setEmbeddingSettings(data);
      setEmbeddingModel(data.model);
    } catch {
      setEmbeddingError("Could not load embedding model settings.");
    }
  }, []);

  useEffect(() => {
    loadEmbedding();
  }, [loadEmbedding]);

  const saveEmbedding = async () => {
    setEmbeddingSaving(true);
    setEmbeddingError("");
    setEmbeddingNotice("");
    try {
      const res = await fetch(`${API}/admin/settings/embedding`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ model: embeddingModel }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Failed to save");
      setEmbeddingNotice(
        "Embedding model saved. Takes effect immediately for new ingestions and searches. " +
        "Builds already ingested under the previous model keep their old embeddings - re-ingest to switch them over."
      );
      await loadEmbedding();
    } catch (err: unknown) {
      setEmbeddingError(err instanceof Error ? err.message : "Failed to save embedding model.");
    } finally {
      setEmbeddingSaving(false);
    }
  };

  const loadSecretKey = useCallback(async () => {
    try {
      const res = await fetch(`${API}/admin/settings/secret-key`, { headers: authHeaders() });
      if (!res.ok) throw new Error("Failed to load");
      setSecretKeyInfo(await res.json());
    } catch {
      setSecretKeyError("Could not load signing key info.");
    }
  }, []);

  useEffect(() => {
    loadSecretKey();
  }, [loadSecretKey]);

  const rotateSecretKey = async (mode: "custom" | "generate") => {
    setRotating(true);
    setSecretKeyError("");
    setSecretKeyNotice("");
    try {
      const res = await fetch(`${API}/admin/settings/secret-key`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify(
          mode === "generate"
            ? { generate: true, confirm: true }
            : { value: secretKeyValue, confirm: true }
        ),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Failed to rotate signing key");
      setSecretKeyInfo(data);
      setSecretKeyValue("");
      setConfirmingRotate(null);
      setSecretKeyNotice("Signing key rotated. Every session, including yours, is now signed out - you'll be redirected to log in.");
      setTimeout(() => {
        localStorage.removeItem("token");
        window.location.href = "/login";
      }, 2500);
    } catch (err: unknown) {
      setSecretKeyError(err instanceof Error ? err.message : "Failed to rotate signing key.");
    } finally {
      setRotating(false);
    }
  };

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
          provider,
          model,
          api_base: apiBase,
          api_key: apiKey || undefined,
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
          provider,
          model,
          api_base: apiBase,
          api_key: apiKey || undefined,
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
            Provider, model and credential used for chat and chart generation. Saving here always takes effect immediately, even if <code>.env</code> also sets a value.
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
        <Field label="Provider" source={settings.provider_source}>
          <select
            className={inputCls}
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
          >
            <option value="">— select a provider —</option>
            {PROVIDERS.map((p) => (
              <option key={p} value={p}>{formatProviderLabel(p)}</option>
            ))}
          </select>
        </Field>

        <Field label="Model" source={settings.model_source}>
          <input
            className={inputCls}
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder={`${provider}/model-name`}
          />
        </Field>

        <Field label="API key" source={settings.api_key_source}>
          <input
            className={inputCls}
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={settings.api_key_set ? settings.api_key_masked : settings.keyless ? "not required for this provider" : "not set"}
          />
        </Field>

        <Field label="API base URL (optional)" source={settings.api_base_source}>
          <input
            className={inputCls}
            value={apiBase}
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

      <div>
        <h2 className="text-xl font-bold">Embedding model</h2>
        <p className="text-sm text-slate-500 dark:text-white/40">
          Local model used to embed ingested documents for semantic/vector search in chat. Kept
          separate from the LLM above - stays local so ingesting doesn&apos;t cost API calls.
        </p>
      </div>

      {embeddingError && <div className="text-red-400 text-sm bg-red-500/[0.08] p-3 rounded-xl border border-red-500/20">{embeddingError}</div>}
      {embeddingNotice && <div className="text-emerald-500 text-sm bg-emerald-500/[0.08] p-3 rounded-xl border border-emerald-500/20">{embeddingNotice}</div>}

      {embeddingSettings && (
        <div className="rounded-xl border border-slate-200 dark:border-white/[0.08] p-5 space-y-4">
          <Field label="Model" source={embeddingSettings.source}>
            <input
              className={inputCls}
              list="embedding-model-options"
              value={embeddingModel}
              onChange={(e) => setEmbeddingModel(e.target.value)}
              placeholder="all-MiniLM-L6-v2"
            />
            <datalist id="embedding-model-options">
              {EMBEDDING_MODELS.map((m) => (
                <option key={m} value={m} />
              ))}
            </datalist>
          </Field>

          <div className="flex flex-wrap gap-3 pt-2">
            <button
              onClick={saveEmbedding}
              disabled={embeddingSaving || !embeddingModel.trim()}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 text-white text-sm font-semibold disabled:opacity-60"
            >
              <Save className="w-4 h-4" /> {embeddingSaving ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
      )}

      <div>
        <h2 className="text-xl font-bold">JWT signing key</h2>
        <p className="text-sm text-slate-500 dark:text-white/40">
          Signs every login token. Rotating it invalidates every currently logged-in session immediately, including your own.
        </p>
      </div>

      {secretKeyError && <div className="text-red-400 text-sm bg-red-500/[0.08] p-3 rounded-xl border border-red-500/20">{secretKeyError}</div>}
      {secretKeyNotice && <div className="text-emerald-500 text-sm bg-emerald-500/[0.08] p-3 rounded-xl border border-emerald-500/20">{secretKeyNotice}</div>}

      <div className="rounded-xl border border-slate-200 dark:border-white/[0.08] p-5 space-y-4">
        {secretKeyInfo && (
          <Field label="Current key" source={secretKeyInfo.source}>
            <div className={`${inputCls} flex items-center gap-2 text-slate-500 dark:text-white/40`}>
              <KeyRound className="w-4 h-4 shrink-0" />
              {secretKeyInfo.masked}
            </div>
          </Field>
        )}

        <Field label="Set a new key (32+ characters)" source="—">
          <input
            className={inputCls}
            type="password"
            value={secretKeyValue}
            onChange={(e) => setSecretKeyValue(e.target.value)}
            placeholder="paste your own random 32+ character value"
          />
        </Field>

        {confirmingRotate ? (
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/[0.08] p-4 space-y-3">
            <div className="flex items-start gap-2 text-sm text-amber-600 dark:text-amber-400">
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>
                This signs out every logged-in user right now, including you. You&apos;ll be sent back to the login page.
                Are you sure?
              </span>
            </div>
            <div className="flex gap-3">
              <button
                onClick={() => rotateSecretKey(confirmingRotate)}
                disabled={rotating}
                className="px-4 py-2 rounded-xl bg-red-600 text-white text-sm font-semibold disabled:opacity-60"
              >
                {rotating ? "Rotating…" : "Yes, rotate and sign everyone out"}
              </button>
              <button
                onClick={() => setConfirmingRotate(null)}
                disabled={rotating}
                className="px-4 py-2 rounded-xl border border-slate-300 dark:border-white/10 text-sm"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap gap-3 pt-2">
            <button
              onClick={() => setConfirmingRotate("custom")}
              disabled={secretKeyValue.trim().length < 32}
              title={secretKeyValue.trim().length < 32 ? "Enter at least 32 characters above first" : ""}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 text-white text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Save className="w-4 h-4" /> Set this key
            </button>
            <button
              onClick={() => setConfirmingRotate("generate")}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-slate-300 dark:border-white/10 text-sm font-semibold hover:border-cyan-500/40"
            >
              <Wand2 className="w-4 h-4" /> Generate one for me instead
            </button>
          </div>
        )}
      </div>
    </div>
    </PageTransition>
  );
}

function Field({
  label,
  source,
  children,
}: {
  label: string;
  source: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-1.5">
        <label className="text-xs font-semibold uppercase tracking-widest text-slate-500 dark:text-white/40">{label}</label>
        <span
          title={
            source === "env"
              ? "Currently set from .env - saving here will override it"
              : source === "database"
              ? "Set from this Settings page"
              : "Using the built-in default"
          }
          className="text-[10px] px-1.5 py-0.5 rounded-full bg-slate-200 dark:bg-white/10 text-slate-500 dark:text-white/40"
        >
          {source}
        </span>
      </div>
      {children}
    </div>
  );
}
