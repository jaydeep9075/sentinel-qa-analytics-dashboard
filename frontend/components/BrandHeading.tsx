"use client";

import type { ReactNode } from "react";
import BrandLockup from "./BrandLockup";

interface BrandHeadingProps {
  /** Page name shown after the Sentinel wordmark, e.g. "Dashboard", "Admin Console". */
  label?: string;
  /**
   * Replaces the tagline on the second line — used by the sub-pages to put a
   * "Back to dashboard" link there instead, which is more useful than a
   * tagline once you're already inside the app.
   */
  subtitle?: ReactNode;
}

/**
 * The signed-in header's brand block: the shared <BrandLockup/> (the official
 * Testrig logo · the Sentinel mark · "Sentinel"), plus the page name after it.
 *
 * The lockup itself lives in one component so the header, the auth cards and
 * the landing page cannot drift apart again — this file only decides what the
 * header adds on top of it: the `/ Dashboard` label, and the choice between the
 * tagline and a sub-page link on the second line.
 */
export default function BrandHeading({ label, subtitle }: BrandHeadingProps) {
  return (
    // shrink-0: when the header runs out of room the selectors in the
    // middle zone scroll, the wordmark does not get squeezed — a truncated
    // brand ("Sentine…") looks broken in a way a scrolled control does not.
    <div className="min-w-0 shrink-0">
      <BrandLockup
        scale={16}
        tagline={!subtitle}
        trailing={
          label && (
            <>
              <span className="text-slate-300 dark:text-white/20" aria-hidden>
                /
              </span>
              <span className="truncate text-sm font-medium text-slate-500 dark:text-white/60">
                {label}
              </span>
            </>
          )
        }
      />
      {subtitle}
    </div>
  );
}
