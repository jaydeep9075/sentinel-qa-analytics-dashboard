const SESSION_STORAGE_KEY = "qa_dashboard_session_id";

export function getSessionId(): string {
  if (typeof window === "undefined") return "";

  const username = (localStorage.getItem("username") || "guest").trim().toLowerCase() || "guest";
  const scopedKey = `${SESSION_STORAGE_KEY}_${username}`;

  let sessionId = localStorage.getItem(scopedKey);
  if (!sessionId) {
    sessionId = typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${username}_${Date.now()}`;
    localStorage.setItem(scopedKey, sessionId);
  }
  return sessionId;
}

export function resetSessionId(): void {
  if (typeof window === "undefined") return;
  const username = (localStorage.getItem("username") || "guest").trim().toLowerCase() || "guest";
  localStorage.removeItem(`${SESSION_STORAGE_KEY}_${username}`);
  localStorage.removeItem(SESSION_STORAGE_KEY);
}
