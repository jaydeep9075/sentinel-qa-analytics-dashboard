"use client";

import Image from "next/image";

/**
 * The TR-Insight mark.
 *
 * Every header, auth card, landing nav and loading skeleton renders this one
 * component, so the mark can only ever change in a single place.
 */

/** public/tr-insight-logo.png is 554×451, so width is derived rather than assumed square. */
const LOGO_ASPECT = 554 / 451;

interface BrandLogoProps {
  className?: string;
  /** Rendered height in px. 26 suits the chat header, 32 the app headers, 52 the loading skeleton. */
  size?: number;
}

export default function BrandLogo({ className = "", size = 32 }: BrandLogoProps) {
  const height = Math.round(size);
  return (
    <Image
      src="/tr-insight-logo.png"
      alt="TR-Insight"
      width={Math.round(height * LOGO_ASPECT)}
      height={height}
      priority
      className={`shrink-0 select-none object-contain ${className}`}
    />
  );
}
