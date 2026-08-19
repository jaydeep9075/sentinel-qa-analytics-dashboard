// Plotly is by far the heaviest chunk in this app (~3.5MB before gzip). The
// gallery loads it through `next/dynamic`, which means the FIRST chart a user
// generates pays the whole download + parse AFTER the request has already
// come back — the generation spinner stops, and the chart lands seconds later
// with nothing on screen in between. Warming the chunk while the user is idle
// (reading the dashboard, typing a prompt) moves that cost off the critical
// path entirely, so by the time a chart arrives the module is already there.
//
// `import()` is memoized by the bundler, so this shares one chunk and one
// module instance with the `dynamic()` call in AIGeneratedChart — warming it
// here makes that dynamic import resolve on the spot.

let plotlyModulePromise: Promise<unknown> | null = null;

export function preloadPlotly(): Promise<unknown> {
  if (typeof window === "undefined") return Promise.resolve(null);
  if (!plotlyModulePromise) {
    plotlyModulePromise = import("react-plotly.js").catch((err) => {
      // A failed warm-up must not poison the real load: clear the memo so the
      // dynamic import can try again on its own.
      plotlyModulePromise = null;
      throw err;
    });
  }
  return plotlyModulePromise;
}

export function isPlotlyWarm(): boolean {
  return plotlyModulePromise !== null;
}

type IdleWindow = Window & {
  requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number;
};

/** Warm Plotly during idle time, never competing with first paint. */
export function schedulePlotlyPreload(delayMs = 400): () => void {
  if (typeof window === "undefined") return () => {};

  let cancelled = false;
  const run = () => {
    if (cancelled) return;
    void preloadPlotly().catch(() => {
      /* warm-up is best effort; the dynamic import still handles real errors */
    });
  };

  const w = window as IdleWindow;
  const timer = window.setTimeout(() => {
    if (typeof w.requestIdleCallback === "function") {
      w.requestIdleCallback(run, { timeout: 2000 });
    } else {
      run();
    }
  }, delayMs);

  return () => {
    cancelled = true;
    window.clearTimeout(timer);
  };
}
