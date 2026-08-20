"use client";

import type { ReactNode } from "react";
import BrandLogo from "./BrandLogo";
import TestrigWordmark from "./TestrigWordmark";

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
 * The Sentinel mark + the "Testrig Sentinel" wordmark, identical everywhere
 * it appears.
 *
 * The company name is set by <TestrigWordmark/> in the brand's own bracketed
 * lettering, one size down from the product name — so the pair reads as
 * "Testrig Sentinel" with the emphasis on the product, without a second logo
 * image competing with the mark.
 *
 * This exists because the dashboard, admin console and account page each had
 * their own copy of the header block, and only the dashboard's carried the
 * full branding — the other two rendered a bare, unglowed logo next to a
 * plain page title, so moving between them looked like moving between two
 * different products. One component means the mark can't drift again.
 */
export default function BrandHeading({ label, subtitle }: BrandHeadingProps) {
  return (
    // shrink-0: when the header runs out of room the selectors in the
    // middle zone scroll, the wordmark does not get squeezed — a truncated
    // brand ("Sentine…") looks broken in a way a scrolled control does not.
    <div className="min-w-0 shrink-0">
      <h1 className="flex items-center gap-2 truncate text-lg font-bold leading-tight tracking-tight">
        <TestrigWordmark />
        <BrandLogo size={24} />
        <span className="text-cyan-500 dark:text-cyan-400">Sentinel</span>
        {label && (
          <>
            <span className="text-slate-300 dark:text-white/20" aria-hidden>
              /
            </span>
            <span className="truncate text-sm font-medium text-slate-500 dark:text-white/60">
              {label}
            </span>
          </>
        )}
      </h1>
      {subtitle ?? (
        <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500 dark:text-white/25">
          QA Intelligence
        </p>
      )}
    </div>
  );
}
