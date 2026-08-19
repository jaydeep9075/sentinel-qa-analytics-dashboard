/** Test output is streamed verbatim to a server, so it is worth one pass to
 * catch the obvious ways a secret ends up in stdout: a curl command echoed
 * by a shell step, a config dump, a token in a URL. This is a safety net for
 * accidents, not a guarantee - it cannot know that `X7fq...` is a password.
 * The patterns are deliberately narrow so ordinary test output survives
 * unmangled; a redactor that mangles assertions is one people switch off. */

const PATTERNS: [RegExp, string][] = [
  // Bearer <token> first: `Authorization: Bearer xyz` also matches the
  // generic key=value rule below, but there the captured "value" is the word
  // "Bearer" and the actual token survives - so this has to win.
  [/(bearer\s+)([A-Za-z0-9._~+/-]{12,}=*)/gi, "$1***"],
  // key=value / "key": "value", for names that are secrets by definition.
  [
    /((?:api[-_]?key|apikey|secret|password|passwd|token|authorization|auth[-_]?token|access[-_]?key)["'\s]*[:=]\s*["']?)([^\s"',&}]{6,})/gi,
    "$1***",
  ],
  // Credentials embedded in a URL: scheme://user:pass@host
  [/(\b[a-z][a-z0-9+.-]*:\/\/[^\s:/@]+:)([^\s@]+)(@)/gi, "$1***$3"],
];

export function redact(text: string): string {
  let out = text;
  for (const [pattern, replacement] of PATTERNS) out = out.replace(pattern, replacement);
  return out;
}

/** A single runaway log line (a 4MB HTML dump from a failed request, a
 * base64 image echoed by a debug helper) would otherwise be pushed through
 * the event pipe, stored, and re-sent to every SSE viewer. Nobody reads past
 * the first screen of one, so cut it and say so. */
export function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return `${text.slice(0, max)}\n… [sentinel: truncated ${text.length - max} more characters]`;
}
