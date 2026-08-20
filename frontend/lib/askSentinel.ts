/**
 * One-way channel for handing a question to the floating chat.
 *
 * A window event rather than lifted state, matching how the chart gallery
 * already talks to the chart input: the panels that want to ask something
 * (today the status drill-down) sit in a different part of the tree from
 * <FloatingChat/>, and threading a callback through the dashboard page for a
 * single button would couple three components to each other for no gain.
 *
 * The constant lives here rather than in either component so neither has to
 * import the other.
 */

export const ASK_SENTINEL_EVENT = "ask-sentinel";

/** Ask the floating chat a question, opening it if it is closed. */
export function askSentinel(question: string): void {
  const text = String(question || "").trim();
  if (!text || typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(ASK_SENTINEL_EVENT, { detail: text }));
}
