"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  X,
  Upload,
  Link as LinkIcon,
  Database,
  Globe,
  FileSpreadsheet,
  FileArchive,
  CheckCircle2,
  XCircle,
  Loader2,
  ArrowLeft,
  PlugZap,
  AlertTriangle,
} from "lucide-react";
import {
  getConnectorOptions,
  uploadIngestFile,
  testConnection,
  startBuildIngestion,
  getIngestStatus,
  type ConnectorOption,
  type ConnectorField,
  type TestConnectionResult,
  type IngestStatus,
} from "@/lib/api";
import { useIngestion } from "@/lib/IngestionContext";
import IngestionProgress from "@/components/IngestionProgress";

type Step = "select" | "configure" | "running" | "done" | "error";

// Used only if GET /ingest/connectors is briefly unreachable when the wizard
// opens - keeps the wizard usable rather than blank. The backend schema is
// still the source of truth and overrides this the moment it responds.
const FALLBACK_CONNECTORS: ConnectorOption[] = [
  {
    id: "allure", name: "Allure Test Results", description: "Ingest test results from Allure artifacts",
    fields: [{ name: "path", type: "text", label: "Path to Allure Results", required: true, placeholder: "/path/to/allure-results" }],
    formats: ["JSON results", "Zip archives", "HTML reports"], auto_detect: true,
  },
  {
    id: "csv", name: "CSV Files", description: "Ingest tabular data from CSV files",
    fields: [{ name: "path", type: "text", label: "Path to CSV File", required: true, placeholder: "/path/to/data.csv" }],
    formats: ["CSV", "TSV"], auto_detect: true,
  },
  {
    id: "excel", name: "Excel Files", description: "Ingest tabular data from Excel workbooks",
    fields: [{ name: "path", type: "text", label: "Path to Excel File", required: true, placeholder: "/path/to/data.xlsx" }],
    formats: ["XLSX", "XLS"], auto_detect: true,
  },
  {
    id: "database", name: "Database", description: "Ingest data from SQL databases",
    fields: [{ name: "connection_string", type: "text", label: "Connection String", required: true, placeholder: "postgresql://user:pass@host:5432/dbname" }],
    formats: ["PostgreSQL", "MySQL", "SQLite"], auto_detect: false,
  },
  {
    id: "api", name: "REST API", description: "Ingest data from REST APIs",
    fields: [{ name: "url", type: "text", label: "API URL", required: true, placeholder: "https://api.example.com/data" }],
    formats: ["REST APIs returning JSON"], auto_detect: false,
  },
];

const CONNECTOR_ICON: Record<string, React.ElementType> = {
  allure: FileArchive,
  csv: FileSpreadsheet,
  excel: FileSpreadsheet,
  database: Database,
  api: Globe,
};

const UPLOAD_ACCEPT: Record<string, string> = {
  allure: ".zip",
  csv: ".csv,.tsv",
  excel: ".xlsx,.xls",
};

const UPLOADABLE = new Set(["allure", "csv", "excel"]);
const TESTABLE = new Set(["database", "api"]);
const POLL_INTERVAL_MS = 2000;
const POLL_CAP_SECONDS = 180;

const inputClass =
  "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-1 focus:ring-cyan-500/40 focus:border-cyan-500/40 dark:border-white/[0.1] dark:bg-black/40 dark:text-white/80 dark:placeholder:text-white/30";
const labelClass = "text-xs font-semibold text-slate-600 dark:text-white/60 mb-1 block";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (buildId: string) => void;
}

export default function AddBuildWizard({ isOpen, onClose, onSuccess }: Props) {
  const { refreshIngestions } = useIngestion();

  const [connectors, setConnectors] = useState<ConnectorOption[]>(FALLBACK_CONNECTORS);
  const [step, setStep] = useState<Step>("select");
  const [selected, setSelected] = useState<ConnectorOption | null>(null);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [displayName, setDisplayName] = useState("");

  const [inputMode, setInputMode] = useState<"upload" | "path">("upload");
  const [uploadedFile, setUploadedFile] = useState<{ filename: string; bytes: number } | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  // 0..1 while a file is transferring, or null when the browser can't
  // compute a total (indeterminate bar rather than a stuck 0%).
  const [uploadPct, setUploadPct] = useState<number | null>(0);
  const [uploadingName, setUploadingName] = useState<string | null>(null);

  const [testResult, setTestResult] = useState<TestConnectionResult | null>(null);
  const [isTesting, setIsTesting] = useState(false);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [buildId, setBuildId] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [pollElapsed, setPollElapsed] = useState(0);
  const [outcome, setOutcome] = useState<"completed" | "timeout" | null>(null);
  // Live pipeline stage from GET /ingest/status — drives IngestionProgress.
  const [jobStatus, setJobStatus] = useState<Pick<IngestStatus, "phase" | "phase_detail" | "rows">>({});

  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  // Rendered via a portal (see the return statement below) because this
  // component is mounted inside the dashboard header, which framer-motion
  // gives a `transform` style - a CSS transform on any ancestor makes
  // `position: fixed` resolve relative to that ancestor instead of the
  // viewport, so without a portal the modal renders clipped near the top
  // of the header instead of centered over the whole page. Portal target
  // must wait for the client mount since document isn't available during SSR.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!isOpen) return;
    getConnectorOptions()
      .then((data) => {
        if (data.connectors?.length) setConnectors(data.connectors);
      })
      .catch(() => {
        // keep the fallback list - the wizard should still work
      });
  }, [isOpen]);

  useEffect(() => {
    if (isOpen) return;
    const t = setTimeout(() => {
      setStep("select");
      setSelected(null);
      setValues({});
      setDisplayName("");
      setInputMode("upload");
      setUploadedFile(null);
      setUploadError(null);
      setUploadPct(0);
      setUploadingName(null);
      setTestResult(null);
      setBuildId(null);
      setErrorMsg(null);
      setPollElapsed(0);
      setOutcome(null);
      setJobStatus({});
    }, 200);
    return () => clearTimeout(t);
  }, [isOpen]);

  useEffect(() => {
    return () => {
      if (pollTimer.current) clearInterval(pollTimer.current);
    };
  }, []);

  if (!isOpen || !mounted) return null;

  const handlePickConnector = (c: ConnectorOption) => {
    const defaults: Record<string, unknown> = {};
    c.fields.forEach((f) => {
      if (f.default !== undefined) defaults[f.name] = f.default;
    });
    setSelected(c);
    setValues(defaults);
    setInputMode("upload");
    setUploadedFile(null);
    setUploadError(null);
    setTestResult(null);
    setStep("configure");
  };

  const setField = (name: string, val: unknown) => setValues((v) => ({ ...v, [name]: val }));

  const requiredFieldsFilled = (): boolean => {
    if (!selected) return false;
    for (const f of selected.fields) {
      if (f.name === "path" && UPLOADABLE.has(selected.id)) continue;
      if (f.name === "body") continue; // optional, POST-only
      if (f.required && !String(values[f.name] ?? "").trim()) return false;
    }
    if (UPLOADABLE.has(selected.id)) {
      return inputMode === "upload" ? !!uploadedFile : !!String(values.path ?? "").trim();
    }
    return true;
  };

  const handleFileSelected = async (file: File) => {
    if (!selected) return;
    setIsUploading(true);
    setUploadError(null);
    setUploadPct(0);
    setUploadingName(file.name);
    try {
      const result = await uploadIngestFile(file, selected.id, setUploadPct);
      setUploadedFile({ filename: result.filename, bytes: result.bytes });
      setField("path", result.staged_path);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Upload failed");
      setUploadedFile(null);
    } finally {
      setIsUploading(false);
      setUploadingName(null);
    }
  };

  const handleTestConnection = async () => {
    if (!selected) return;
    setIsTesting(true);
    setTestResult(null);
    try {
      const result = await testConnection(selected.id, values);
      setTestResult(result);
    } catch (err) {
      setTestResult({ success: false, message: err instanceof Error ? err.message : "Test failed" });
    } finally {
      setIsTesting(false);
    }
  };

  const pollStatus = (id: string) => {
    let elapsed = 0;
    pollTimer.current = setInterval(async () => {
      elapsed += POLL_INTERVAL_MS / 1000;
      setPollElapsed(elapsed);
      if (elapsed >= POLL_CAP_SECONDS) {
        if (pollTimer.current) clearInterval(pollTimer.current);
        setOutcome("timeout");
        setStep("done");
        return;
      }
      try {
        const status = await getIngestStatus(id);
        setJobStatus({ phase: status.phase, phase_detail: status.phase_detail, rows: status.rows });
        if (status.status === "completed") {
          if (pollTimer.current) clearInterval(pollTimer.current);
          await refreshIngestions();
          onSuccess(id);
          setOutcome("completed");
          setStep("done");
        } else if (status.status === "failed") {
          if (pollTimer.current) clearInterval(pollTimer.current);
          setErrorMsg(status.error || "Ingestion failed");
          setStep("error");
        }
      } catch {
        // transient poll failure - keep trying until the cap
      }
    }, POLL_INTERVAL_MS);
  };

  const handleSubmit = async () => {
    if (!selected) return;
    setIsSubmitting(true);
    setErrorMsg(null);
    try {
      const result = await startBuildIngestion({
        connector_type: selected.id,
        config: values,
        display_name: displayName.trim() || undefined,
      });
      setBuildId(result.build_id);
      setPollElapsed(0);
      setJobStatus({});
      setStep("running");
      pollStatus(result.build_id);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to start ingestion");
      setStep("error");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleClose = () => {
    if (pollTimer.current) clearInterval(pollTimer.current);
    onClose();
  };

  const renderFieldInput = (field: ConnectorField) => {
    const value = values[field.name];
    if (field.type === "checkbox") {
      return (
        <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-white/70 cursor-pointer">
          <input
            type="checkbox"
            checked={Boolean(value ?? field.default ?? false)}
            onChange={(e) => setField(field.name, e.target.checked)}
            className="rounded border-slate-300"
          />
          {field.label}
        </label>
      );
    }
    if (field.type === "select") {
      return (
        <select
          value={(value as string) ?? (field.default as string) ?? ""}
          onChange={(e) => setField(field.name, e.target.value)}
          className={inputClass}
        >
          {field.options?.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      );
    }
    if (field.type === "textarea") {
      return (
        <textarea
          value={(value as string) ?? ""}
          onChange={(e) => setField(field.name, e.target.value)}
          placeholder={field.placeholder}
          rows={3}
          className={`${inputClass} font-mono text-xs`}
        />
      );
    }
    if (field.type === "number") {
      return (
        <input
          type="number"
          value={(value as number) ?? (field.default as number) ?? ""}
          onChange={(e) => setField(field.name, e.target.value === "" ? "" : Number(e.target.value))}
          placeholder={field.placeholder}
          className={inputClass}
        />
      );
    }
    return (
      <input
        type="text"
        value={(value as string) ?? ""}
        onChange={(e) => setField(field.name, e.target.value)}
        placeholder={field.placeholder}
        className={inputClass}
      />
    );
  };

  const renderField = (field: ConnectorField) => {
    // POST-only body field: don't show it while method is GET.
    if (field.name === "body" && String(values.method ?? "GET").toUpperCase() !== "POST") {
      return null;
    }
    if (field.type === "checkbox") {
      return <div key={field.name} className="mb-3">{renderFieldInput(field)}</div>;
    }
    return (
      <div key={field.name} className="mb-3">
        <label className={labelClass}>
          {field.label}
          {field.required && <span className="text-red-500 ml-0.5">*</span>}
        </label>
        {renderFieldInput(field)}
        {field.help && <p className="mt-1 text-[11px] text-slate-400 dark:text-white/30">{field.help}</p>}
      </div>
    );
  };

  const isUploadable = selected ? UPLOADABLE.has(selected.id) : false;
  const isTestable = selected ? TESTABLE.has(selected.id) : false;
  const nonPathFields = selected ? selected.fields.filter((f) => f.name !== "path") : [];

  return createPortal(
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.15 }}
        className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
        onClick={handleClose}
      >
        <motion.div
          initial={{ opacity: 0, y: 16, scale: 0.96 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 16, scale: 0.96 }}
          transition={{ type: "spring", stiffness: 320, damping: 28 }}
          onClick={(e) => e.stopPropagation()}
          className="w-full max-w-lg max-h-[88vh] overflow-y-auto rounded-xl border border-slate-200 bg-white p-5 shadow-[0_20px_50px_rgba(15,23,42,0.3)] dark:border-white/[0.08] dark:bg-black/95"
        >
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              {step === "configure" && (
                <button
                  onClick={() => setStep("select")}
                  className="p-1 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 dark:text-white/35 dark:hover:text-white dark:hover:bg-white/[0.08]"
                >
                  <ArrowLeft className="w-4 h-4" />
                </button>
              )}
              <h3 className="text-sm font-semibold uppercase tracking-widest text-slate-500 dark:text-white/40">
                Add New Build
              </h3>
            </div>
            <button
              onClick={handleClose}
              className="p-1 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 dark:text-white/35 dark:hover:text-white dark:hover:bg-white/[0.08]"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Step 1: pick connector */}
          {step === "select" && (
            <div className="grid grid-cols-1 gap-2">
              {connectors.map((c, i) => {
                const Icon = CONNECTOR_ICON[c.id] || Database;
                return (
                  <motion.button
                    key={c.id}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.25, delay: i * 0.04, ease: [0.22, 1, 0.36, 1] }}
                    whileHover={{ x: 3 }}
                    onClick={() => handlePickConnector(c)}
                    className="group flex items-start gap-3 rounded-lg border border-slate-200 p-3 text-left hover:border-cyan-500/40 hover:bg-cyan-50/50 transition-colors dark:border-white/[0.08] dark:hover:border-cyan-500/30 dark:hover:bg-cyan-500/[0.04]"
                  >
                    <div className="rounded-lg bg-slate-100 p-2 transition-transform group-hover:scale-110 dark:bg-white/[0.06]">
                      <Icon className="w-4 h-4 text-cyan-500" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-slate-800 dark:text-white/85">{c.name}</p>
                      <p className="text-xs text-slate-500 dark:text-white/40">{c.description}</p>
                    </div>
                  </motion.button>
                );
              })}
            </div>
          )}

          {/* Step 2: configure */}
          {step === "configure" && selected && (
            <div>
              {isUploadable && (
                <div className="mb-4">
                  <div className="flex gap-1 mb-2 rounded-lg bg-slate-100 p-1 dark:bg-white/[0.05] w-fit">
                    <button
                      onClick={() => setInputMode("upload")}
                      className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition-all ${
                        inputMode === "upload"
                          ? "bg-white text-slate-800 shadow dark:bg-white/10 dark:text-white"
                          : "text-slate-500 dark:text-white/40"
                      }`}
                    >
                      <Upload className="w-3.5 h-3.5" /> Upload
                    </button>
                    <button
                      onClick={() => setInputMode("path")}
                      className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition-all ${
                        inputMode === "path"
                          ? "bg-white text-slate-800 shadow dark:bg-white/10 dark:text-white"
                          : "text-slate-500 dark:text-white/40"
                      }`}
                    >
                      <LinkIcon className="w-3.5 h-3.5" /> Server path
                    </button>
                  </div>

                  {inputMode === "upload" ? (
                    <div>
                      <div
                        onClick={() => { if (!isUploading) fileInputRef.current?.click(); }}
                        onDragOver={(e) => e.preventDefault()}
                        onDrop={(e) => {
                          e.preventDefault();
                          const file = e.dataTransfer.files?.[0];
                          if (file) handleFileSelected(file);
                        }}
                        className="flex flex-col items-center justify-center gap-1.5 rounded-lg border-2 border-dashed border-slate-300 p-5 text-center cursor-pointer hover:border-cyan-500/40 hover:bg-cyan-50/30 transition-all dark:border-white/[0.12] dark:hover:border-cyan-500/30 dark:hover:bg-cyan-500/[0.03]"
                      >
                        {isUploading ? (
                          <div className="w-full">
                            <div className="flex items-center justify-center gap-2">
                              <motion.span
                                animate={{ y: [0, -3, 0] }}
                                transition={{ duration: 1.1, repeat: Infinity, ease: "easeInOut" }}
                              >
                                <Upload className="w-5 h-5 text-cyan-500" />
                              </motion.span>
                              <p className="truncate text-xs font-medium text-slate-600 dark:text-white/60">
                                {uploadingName ?? "Uploading"}
                              </p>
                            </div>
                            <div className="relative mt-3 h-1.5 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-white/[0.08]">
                              {uploadPct === null ? (
                                // Indeterminate: browser gave no total, so a
                                // percentage would be invented.
                                <motion.div
                                  className="absolute inset-y-0 w-1/3 rounded-full bg-gradient-to-r from-transparent via-cyan-500 to-transparent"
                                  animate={{ left: ["-33%", "100%"] }}
                                  transition={{ duration: 1.2, repeat: Infinity, ease: "linear" }}
                                />
                              ) : (
                                <motion.div
                                  className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-cyan-500 to-blue-500"
                                  animate={{ width: `${Math.round(uploadPct * 100)}%` }}
                                  transition={{ ease: "easeOut", duration: 0.25 }}
                                />
                              )}
                            </div>
                            <p className="mt-1.5 font-mono text-[11px] tabular-nums text-slate-400 dark:text-white/30">
                              {uploadPct === null ? "Transferring…" : `${Math.round(uploadPct * 100)}%`}
                            </p>
                          </div>
                        ) : uploadedFile ? (
                          <>
                            <motion.span
                              initial={{ scale: 0.4, opacity: 0 }}
                              animate={{ scale: 1, opacity: 1 }}
                              transition={{ type: "spring", stiffness: 380, damping: 18 }}
                            >
                              <CheckCircle2 className="w-5 h-5 text-emerald-500" />
                            </motion.span>
                            <p className="text-xs font-semibold text-slate-700 dark:text-white/70">{uploadedFile.filename}</p>
                            <p className="text-[11px] text-slate-400 dark:text-white/30">
                              {(uploadedFile.bytes / (1024 * 1024)).toFixed(2)} MB — click to replace
                            </p>
                          </>
                        ) : (
                          <>
                            <Upload className="w-5 h-5 text-slate-400 dark:text-white/30" />
                            <p className="text-xs text-slate-500 dark:text-white/40">
                              Drag a file here, or click to browse
                            </p>
                          </>
                        )}
                        <input
                          ref={fileInputRef}
                          type="file"
                          accept={UPLOAD_ACCEPT[selected.id]}
                          className="hidden"
                          onChange={(e) => {
                            const file = e.target.files?.[0];
                            if (file) handleFileSelected(file);
                          }}
                        />
                      </div>
                      {uploadError && <p className="mt-1.5 text-xs text-red-600 dark:text-red-400">{uploadError}</p>}
                    </div>
                  ) : (
                    <div>
                      <label className={labelClass}>Server Path<span className="text-red-500 ml-0.5">*</span></label>
                      <input
                        type="text"
                        value={(values.path as string) ?? ""}
                        onChange={(e) => setField("path", e.target.value)}
                        placeholder={selected.fields.find((f) => f.name === "path")?.placeholder}
                        className={inputClass}
                      />
                    </div>
                  )}
                </div>
              )}

              {nonPathFields.map(renderField)}

              {isTestable && (
                <div className="mb-4 rounded-lg border border-slate-200 p-3 dark:border-white/[0.08]">
                  <button
                    onClick={handleTestConnection}
                    disabled={isTesting || !requiredFieldsFilled()}
                    className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold border border-slate-300 text-slate-700 hover:bg-slate-100 disabled:opacity-50 disabled:cursor-not-allowed dark:border-white/[0.12] dark:text-white/70 dark:hover:bg-white/[0.07]"
                  >
                    {isTesting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <PlugZap className="w-3.5 h-3.5" />}
                    {isTesting ? "Testing..." : "Test Connection"}
                  </button>
                  {testResult && (
                    <div className={`mt-2 text-xs ${testResult.success ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}>
                      <div className="flex items-start gap-1.5">
                        {testResult.success ? <CheckCircle2 className="w-3.5 h-3.5 mt-0.5 shrink-0" /> : <XCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />}
                        <div>
                          {testResult.success ? (
                            <>
                              {testResult.tables && <p>Connected. {testResult.table_count} table(s): {testResult.tables.slice(0, 8).join(", ")}{(testResult.table_count || 0) > 8 ? "…" : ""}</p>}
                              {testResult.status_code !== undefined && <p>HTTP {testResult.status_code} · {testResult.content_type} {testResult.is_json === false && "(not JSON)"}</p>}
                              {testResult.preview && <pre className="mt-1 whitespace-pre-wrap break-all text-[10px] text-slate-500 dark:text-white/40">{testResult.preview}</pre>}
                            </>
                          ) : (
                            <p>{testResult.message}</p>
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                  {!testResult && (
                    <p className="mt-2 flex items-center gap-1.5 text-[11px] text-amber-600 dark:text-amber-400">
                      <AlertTriangle className="w-3 h-3" /> Not tested yet — you can still ingest without testing.
                    </p>
                  )}
                </div>
              )}

              <div className="mb-4">
                <label className={labelClass}>Build name (optional)</label>
                <input
                  type="text"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="e.g. Nightly Regression Run"
                  className={inputClass}
                />
              </div>

              {errorMsg && step === "configure" && (
                <p className="mb-3 text-xs text-red-600 dark:text-red-400">{errorMsg}</p>
              )}

              <div className="flex justify-end">
                <button
                  onClick={handleSubmit}
                  disabled={isSubmitting || !requiredFieldsFilled()}
                  className="flex items-center gap-1.5 rounded-lg px-4 py-2 text-xs font-semibold text-white bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-all active:scale-95"
                >
                  {isSubmitting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  {isSubmitting ? "Starting..." : "Ingest"}
                </button>
              </div>
            </div>
          )}

          {/* Step 3: running */}
          {step === "running" && (
            <div className="py-2">
              <div className="mb-5 text-center">
                <p className="text-sm font-semibold text-slate-700 dark:text-white/80">
                  Ingesting {displayName.trim() || buildId || "build"}
                </p>
                {selected && (
                  <p className="mt-0.5 text-[11px] text-slate-400 dark:text-white/30">
                    via {selected.name}
                  </p>
                )}
              </div>

              <IngestionProgress
                phase={jobStatus.phase}
                detail={jobStatus.phase_detail}
                rows={jobStatus.rows}
                elapsedSeconds={Math.round(pollElapsed)}
              />

              <p className="mt-4 text-center text-[11px] text-slate-400 dark:text-white/30">
                You can close this — ingestion keeps running in the background and the new build will
                appear in the build list once it&rsquo;s done.
              </p>
              <div className="mt-3 flex justify-center">
                <button
                  onClick={handleClose}
                  className="rounded-lg px-3 py-1.5 text-xs font-semibold border border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-white/[0.12] dark:text-white/70 dark:hover:bg-white/[0.07]"
                >
                  Close
                </button>
              </div>
            </div>
          )}

          {/* Step 4a: done */}
          {step === "done" && (
            <div className="flex flex-col items-center gap-3 py-6 text-center">
              {outcome === "completed" ? (
                <>
                  <div className="w-full pb-2">
                    <IngestionProgress
                      done
                      rows={jobStatus.rows}
                      elapsedSeconds={Math.round(pollElapsed)}
                    />
                  </div>
                  <motion.span
                    initial={{ scale: 0.3, opacity: 0 }}
                    animate={{ scale: 1, opacity: 1 }}
                    transition={{ type: "spring", stiffness: 320, damping: 16 }}
                    className="relative mt-2"
                  >
                    {/* one-shot ring that expands out of the tick */}
                    <motion.span
                      className="absolute inset-0 rounded-full border-2 border-emerald-500"
                      initial={{ opacity: 0.6, scale: 1 }}
                      animate={{ opacity: 0, scale: 2.4 }}
                      transition={{ duration: 0.9, ease: "easeOut" }}
                    />
                    <CheckCircle2 className="w-8 h-8 text-emerald-500" />
                  </motion.span>
                  <p className="text-sm font-semibold text-slate-700 dark:text-white/80">Build ready</p>
                  <p className="text-xs text-slate-400 dark:text-white/30">The new build is selected and ready to explore.</p>
                </>
              ) : (
                <>
                  <Loader2 className="w-8 h-8 text-amber-500" />
                  <p className="text-sm font-semibold text-slate-700 dark:text-white/80">Still running</p>
                  <p className="text-xs text-slate-400 dark:text-white/30 max-w-xs">
                    This is taking longer than expected but is still running in the background. It&rsquo;ll show
                    up in the build list once it finishes.
                  </p>
                </>
              )}
              <button
                onClick={handleClose}
                className="mt-1 rounded-lg px-4 py-2 text-xs font-semibold text-white bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 transition-all"
              >
                Done
              </button>
            </div>
          )}

          {/* Step 4b: error */}
          {step === "error" && (
            <div className="flex flex-col items-center gap-3 py-6 text-center">
              <XCircle className="w-8 h-8 text-red-500" />
              <p className="text-sm font-semibold text-slate-700 dark:text-white/80">Ingestion failed</p>
              <p className="text-xs text-red-600 dark:text-red-400 max-w-xs break-words">{errorMsg}</p>
              <div className="flex gap-2 mt-1">
                <button
                  onClick={handleClose}
                  className="rounded-lg px-3 py-1.5 text-xs font-semibold border border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-white/[0.12] dark:text-white/70 dark:hover:bg-white/[0.07]"
                >
                  Close
                </button>
                <button
                  onClick={() => setStep("configure")}
                  className="rounded-lg px-3 py-1.5 text-xs font-semibold text-white bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 transition-all"
                >
                  Try Again
                </button>
              </div>
            </div>
          )}
        </motion.div>
      </motion.div>
    </AnimatePresence>,
    document.body
  );
}
