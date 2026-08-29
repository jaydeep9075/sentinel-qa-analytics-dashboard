"use client";

/**
 * The TR-Insight mark: just the letters "TR", set in Testrig's brand green.
 * TR already reads as Testrig on its own, so there is no separate boxed icon
 * and no separate company wordmark next to it — these two green letters
 * *are* the mark.
 *
 * Every header, auth card, landing nav and loading skeleton renders this one
 * component, so the mark can only ever change in a single place.
 */

/** Testrig brand green. */
export const TR_GREEN = "#20BC75";

interface BrandLogoProps {
  className?: string;
  /** Rendered font-size in px. 32 suits the app headers, 52 the loading skeleton. */
  size?: number;
}

export default function BrandLogo({ className = "", size = 32 }: BrandLogoProps) {
  return (
    <span
      aria-label="TR-Insight"
      style={{ fontSize: size, color: TR_GREEN }}
      className={`shrink-0 select-none font-extrabold leading-none tracking-tight ${className}`}
    >
      TR
    </span>
  );
}
