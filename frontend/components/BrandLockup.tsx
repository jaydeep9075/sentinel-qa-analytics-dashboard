"use client";

import type { ReactNode } from "react";

import BrandLogo from "./BrandLogo";
import TestrigLogo, { TESTRIG_LOGO_RATIO } from "./TestrigLogo";
import { BRAND_TAGLINE, SHOW_TESTRIG_LOGO } from "@/lib/brand";

/**
 * The one brand lockup: `Testrig` (official logo) · Sentinel mark · "Sentinel",
 * with the tagline set on its own line under the Sentinel block.
 *
 * Every surface that introduces the product — the signed-in header, the sign-in
 * and registration cards, the landing nav and footer — renders this, so the
 * three pieces can only ever be arranged one way and at one set of proportions.
 *
 * Everything is driven by a single `scale`, which is the *optical* height the
 * lockup should read at. The two names are set to match each other rather than
 * to share a raw pixel value, because they are measured differently:
 *
 *   - the Testrig logo is all-caps artwork whose letters fill ~93% of its box,
 *     so at height H its caps are 0.93H;
 *   - "Sentinel" is type, and Inter's cap height is ~0.73em, so at font-size F
 *     its caps are 0.73F.
 *
 * Setting both from the same number is what made the wordmark look oversized
 * next to a product name that looked shrunken. The multipliers below land the
 * two cap heights within a couple of percent of each other.
 */

/** Gap between the lockup's pieces, in px — also drives the tagline's indent. */
const PIECE_GAP = 10;

interface BrandLockupProps {
  /** Optical height of the lockup in px. 16 suits the app header, 22 an auth card. */
  scale?: number;
  /** Show the tagline line under the Sentinel block. */
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
  const logoHeight = Math.round(scale * 0.92);
  const nameSize = Math.round(scale * 1.2);
  // The mark is a solid shape, so it reads heavier than type at the same height
  // and needs to sit just above the cap line to look level with it.
  const markSize = Math.round(scale * 1.25);

  // Start the tagline where the Sentinel block starts: past the logo, the gap,
  // the 1px divider and the gap after it. Derived from the logo's own ratio, so
  // it stays aligned at every scale without measuring the DOM. With the Testrig
  // logo hidden the Sentinel block starts at the left edge, so there is nothing
  // to indent past.
  const taglineIndent = SHOW_TESTRIG_LOGO
    ? Math.round(logoHeight * TESTRIG_LOGO_RATIO + PIECE_GAP * 2 + 1)
    : 0;

  return (
    <div className={`min-w-0 ${className}`}>
      <div className="flex items-center" style={{ gap: PIECE_GAP }}>
        {/* Both the company logo and the hairline that separates it from the
            product go together: with no Testrig mark there is nothing for the
            divider to divide. */}
        {SHOW_TESTRIG_LOGO && (
          <>
            <TestrigLogo height={logoHeight} />
            <span
              aria-hidden
              className="w-px shrink-0 bg-slate-300 dark:bg-white/15"
              style={{ height: Math.round(scale * 1.15) }}
            />
          </>
        )}

        <BrandLogo size={markSize} />
        <span
          className="font-bold leading-none tracking-tight text-cyan-600 dark:text-cyan-400"
          style={{ fontSize: nameSize, marginLeft: -PIECE_GAP + 6 }}
        >
          Sentinel
        </span>
        {trailing}
      </div>

      {tagline && (
        <p
          className="truncate font-medium tracking-wide text-slate-500 dark:text-white/40"
          style={{
            paddingLeft: taglineIndent,
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
