"use client";

import Image from "next/image";

/** Intrinsic size of public/logo.png — the mark is wider than it is tall. */
const LOGO_W = 554;
const LOGO_H = 451;

interface BrandLogoProps {
  className?: string;
  /**
   * Rendered height in px; the width follows the mark's own aspect ratio so
   * it never squashes. 32 suits the app headers, 44 the auth cards.
   */
  size?: number;
}

/**
 * The Sentinel mark. Every header, auth card and landing nav renders this one
 * component, so the logo can only ever change in a single place.
 */
export default function BrandLogo({ className = "", size = 32 }: BrandLogoProps) {
  return (
    <Image
      src="/logo.png"
      alt="Sentinel"
      width={LOGO_W}
      height={LOGO_H}
      priority
      sizes={`${Math.round((size * LOGO_W) / LOGO_H)}px`}
      style={{ height: size, width: "auto" }}
      className={`brand-mark shrink-0 select-none object-contain ${className}`}
    />
  );
}
