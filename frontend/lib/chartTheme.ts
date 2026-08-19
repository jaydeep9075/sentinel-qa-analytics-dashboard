/**
 * chartTheme.ts — re-theme a server-rendered Plotly figure on the client.
 *
 * The backend renders one figure and has no idea which theme the viewer is in
 * (and the viewer can toggle it after the chart is drawn, so there is no answer
 * it could bake in). Previously charts were hardcoded to dark-mode ink —
 * #CBD5E1 tick labels on a white card in light mode, which is roughly 1.6:1
 * contrast and effectively unreadable.
 *
 * So the backend emits the LIGHT rendering plus, in `layout.meta.sentinel`, the
 * palette and chrome for BOTH modes and a per-trace slot map. This module
 * applies the right one. Colour is remapped by SLOT, not by matching hex
 * values, so a series keeps its identity across a theme toggle — the whole
 * point of assigning categorical hues in fixed order.
 */

export type ChartMode = "light" | "dark";

interface Chrome {
  ink: string;
  ink_secondary: string;
  muted: string;
  grid: string;
  baseline: string;
  surface: string;
  border: string;
}

interface ModeTheme {
  palette: string[];
  other: string;
  sequential: Array<[number, string]>;
  diverging: Array<[number, string]>;
  chrome: Chrome;
}

export interface SentinelChartMeta {
  insight?: string;
  scope?: string;
  chart_type?: string;
  measure?: string;
  dimension?: string;
  row_count?: number;
  truncated?: boolean;
  table?: {
    columns: Array<{ key: string; label: string; unit: string }>;
    rows: string[][];
  };
  theme?: {
    light: ModeTheme;
    dark: ModeTheme;
    status: Record<string, string>;
  };
}

type AnyRecord = Record<string, unknown>;

export function readSentinelMeta(layout: unknown): SentinelChartMeta | null {
  const meta = (layout as AnyRecord | null)?.meta as AnyRecord | undefined;
  const sentinel = meta?.sentinel as SentinelChartMeta | undefined;
  return sentinel ?? null;
}

/** Slot -> colour. Status slots are mode-invariant by design (they ship with a
 *  label, so they never rely on hue alone) and pass through unchanged. */
function colorForSlot(slot: unknown, theme: ModeTheme, status: Record<string, string>): string | null {
  if (typeof slot === "number") {
    return theme.palette[slot % theme.palette.length] ?? null;
  }
  if (typeof slot === "string") {
    if (slot === "other") return theme.other;
    if (slot.startsWith("status:")) {
      return status[slot.slice("status:".length)] ?? null;
    }
  }
  return null;
}

function applyTraceColors(
  trace: AnyRecord,
  theme: ModeTheme,
  status: Record<string, string>,
  surface: string,
): AnyRecord {
  const meta = trace.meta as AnyRecord | undefined;
  const next: AnyRecord = { ...trace };

  // Multi-slot traces (pie / treemap / funnel) carry one slot per slice.
  const slots = meta?.slots as unknown[] | undefined;
  if (Array.isArray(slots)) {
    const colors = slots.map(
      (s, i) => colorForSlot(s, theme, status) ?? theme.palette[i % theme.palette.length],
    );
    next.marker = { ...(trace.marker as AnyRecord), colors, line: { width: 2, color: surface } };
    return next;
  }

  if (meta?.scale === "sequential") {
    next.colorscale = theme.sequential;
    return next;
  }

  const slot = meta?.slot;
  if (slot === undefined || slot === null) return next;

  // A per-point slot array on a single-series trace (status-coloured bars).
  if (Array.isArray(slot)) {
    const colors = slot.map(
      (s, i) => colorForSlot(s, theme, status) ?? theme.palette[i % theme.palette.length],
    );
    next.marker = { ...(trace.marker as AnyRecord), color: colors, line: { width: 0 } };
    return next;
  }

  const color = colorForSlot(slot, theme, status);
  if (!color) return next;

  const existingMarker = (trace.marker as AnyRecord) ?? {};
  next.marker = { ...existingMarker, color };
  // Markers on lines/scatter carry a surface-coloured ring to separate
  // overlapping points; that ring has to follow the theme too.
  if (existingMarker.line && typeof existingMarker.line === "object") {
    const ml = existingMarker.line as AnyRecord;
    if (ml.color) next.marker = { ...(next.marker as AnyRecord), line: { ...ml, color: surface } };
  }
  if (trace.line && typeof trace.line === "object") {
    next.line = { ...(trace.line as AnyRecord), color };
  }
  if (trace.fillcolor) {
    next.fillcolor = withAlpha(color, 0.15);
  }
  if (trace.textfont && typeof trace.textfont === "object") {
    // Value labels are text and wear text ink, never the series colour.
    next.textfont = { ...(trace.textfont as AnyRecord), color: theme.chrome.ink_secondary };
  }
  return next;
}

function withAlpha(hex: string, alpha: number): string {
  const h = hex.replace("#", "");
  if (h.length !== 6) return hex;
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

function themeAxis(axis: AnyRecord | undefined, chrome: Chrome): AnyRecord | undefined {
  if (!axis || typeof axis !== "object") return axis;
  const next: AnyRecord = { ...axis };
  if (axis.tickfont) next.tickfont = { ...(axis.tickfont as AnyRecord), color: chrome.muted };
  if (axis.title && typeof axis.title === "object") {
    const t = axis.title as AnyRecord;
    next.title = { ...t, font: { ...((t.font as AnyRecord) ?? {}), color: chrome.ink_secondary } };
  }
  if (axis.gridcolor) next.gridcolor = chrome.grid;
  if (axis.linecolor) next.linecolor = chrome.baseline;
  return next;
}

/**
 * Returns a theme-adjusted copy of `{data, layout}`. Pure — never mutates the
 * figure it was handed, so React can hold the original and re-derive on every
 * theme change without the two drifting apart.
 */
export function themeFigure(
  data: unknown[],
  layout: AnyRecord,
  mode: ChartMode,
): { data: unknown[]; layout: AnyRecord } {
  const sentinel = readSentinelMeta(layout);
  const themes = sentinel?.theme;
  if (!themes) {
    // A chart from before this pipeline (chart history) has no theme payload.
    // Leave it exactly as it was rather than half-theming it into something
    // worse than either mode.
    return { data, layout };
  }

  const theme = mode === "dark" ? themes.dark : themes.light;
  const chrome = theme.chrome;
  const status = themes.status ?? {};

  const nextData = data.map((t) =>
    applyTraceColors(t as AnyRecord, theme, status, chrome.surface),
  );

  const nextLayout: AnyRecord = { ...layout };
  nextLayout.font = { ...((layout.font as AnyRecord) ?? {}), color: chrome.ink };
  nextLayout.colorway = theme.palette;

  if (layout.title && typeof layout.title === "object") {
    const title = layout.title as AnyRecord;
    const nextTitle: AnyRecord = {
      ...title,
      font: { ...((title.font as AnyRecord) ?? {}), color: chrome.ink },
    };
    if (title.subtitle && typeof title.subtitle === "object") {
      const st = title.subtitle as AnyRecord;
      nextTitle.subtitle = {
        ...st,
        font: { ...((st.font as AnyRecord) ?? {}), color: chrome.ink_secondary },
      };
    }
    nextLayout.title = nextTitle;
  }

  for (const key of ["xaxis", "yaxis", "xaxis2", "yaxis2"]) {
    const themed = themeAxis(layout[key] as AnyRecord | undefined, chrome);
    if (themed) nextLayout[key] = themed;
  }

  if (layout.polar && typeof layout.polar === "object") {
    const polar = layout.polar as AnyRecord;
    nextLayout.polar = {
      ...polar,
      radialaxis: themeAxis(polar.radialaxis as AnyRecord, chrome),
      angularaxis: themeAxis(polar.angularaxis as AnyRecord, chrome),
    };
  }

  nextLayout.hoverlabel = {
    ...((layout.hoverlabel as AnyRecord) ?? {}),
    bgcolor: chrome.surface,
    bordercolor: chrome.border,
    font: { ...(((layout.hoverlabel as AnyRecord)?.font as AnyRecord) ?? {}), color: chrome.ink },
  };

  if (layout.legend && typeof layout.legend === "object") {
    const legend = layout.legend as AnyRecord;
    nextLayout.legend = {
      ...legend,
      font: { ...((legend.font as AnyRecord) ?? {}), color: chrome.ink_secondary },
    };
  }

  if (Array.isArray(layout.annotations)) {
    nextLayout.annotations = (layout.annotations as AnyRecord[]).map((a) => {
      const font = (a.font as AnyRecord) ?? {};
      // Threshold and endpoint annotations are deliberately coloured (a green
      // target rule, a series-coloured endpoint) — only recolour the ones
      // wearing plain ink.
      const isInk =
        font.color === "#0b0b0b" || font.color === "#52514e" || font.color === "#898781";
      return isInk ? { ...a, font: { ...font, color: chrome.ink_secondary } } : a;
    });
  }

  if (Array.isArray(layout.shapes)) {
    nextLayout.shapes = (layout.shapes as AnyRecord[]).map((s) => {
      const line = (s.line as AnyRecord) ?? {};
      return line.color === "#898781" ? { ...s, line: { ...line, color: chrome.muted } } : s;
    });
  }

  return { data: nextData, layout: nextLayout };
}
