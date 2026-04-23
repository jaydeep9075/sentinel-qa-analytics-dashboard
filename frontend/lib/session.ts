const SESSION_STORAGE_KEY = "qa_dashboard_session_id";

export function getSessionId(): string {
  if (typeof window === "undefined") return "";

  let sessionId = localStorage.getItem("username");
  if (!sessionId) {
    sessionId = "guest_session";
  }
  return sessionId;
}

export function resetSessionId(): void {
  localStorage.removeItem(SESSION_STORAGE_KEY);
}
