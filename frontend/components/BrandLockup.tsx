"use client";

import type { ReactNode } from "react";

import BrandLogo from "./BrandLogo";
import { BRAND_TAGLINE } from "@/lib/brand";

/**
 * The one brand lockup: green "TR" · "-Insight", with the tagline set on its
 * own line underneath.
 *
 * TR already reads as Testrig on its own, so there is no separate company
 * wordmark or icon here — just the two-tone product name, "TR" in Testrig
 * green and "-Insight" in the product's own accent. Every surface that
 * introduces the product — the signed-in header, the sign-in and
 * registration cards, the landing nav and footer — renders this, so it can
 * only ever be arranged one way and at one set of proportions.
 *
 * `scale` is the optical height (px) the wordmark should read at; "TR" and
 * "-Insight" share it exactly, so the two halves sit on one baseline at one
 * size instead of drifting apart.
 */

interface BrandLockupProps {
  /** Optical height of the lockup in px. 16 suits the app header, 22 an auth card. */
  scale?: number;
  /** Show the tagline line under the wordmark. */
  tagline?: boolean;
  /**
   * Rendered inside the lockup row, after the product name — the signed-in
   * header puts its "/ Dashboard" page label here so the label sits on the
   * lockup's own baseline instead of being centred against the two-line block.
   */
  trailing?: ReactNode;
  className?: string;
}

export default function BrandLockup({
  scale = 16,
  tagline = true,
  trailing,
  className = "",
}: BrandLockupProps) {
  const nameSize = Math.round(scale * 1.2);

  return (
    <div className={`min-w-0 ${className}`}>
      <div className="flex items-baseline" style={{ gap: 8 }}>
        <span className="inline-flex items-baseline">
          <BrandLogo size={nameSize} />
          <span
            className="font-bold leading-none tracking-tight text-cyan-600 dark:text-cyan-400"
            style={{ fontSize: nameSize }}
          >
            -Insight
          </span>
        </span>
        {trailing}
      </div>

      {tagline && (
        <p
          className="truncate font-medium tracking-wide text-slate-500 dark:text-white/40"
          style={{
            marginTop: Math.max(3, Math.round(scale * 0.2)),
            fontSize: Math.max(10, Math.round(scale * 0.68)),
          }}
        >
          {BRAND_TAGLINE}
        </p>
      )}
    </div>
  );
}
