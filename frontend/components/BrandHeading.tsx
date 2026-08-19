"use client";

import type { ReactNode } from "react";
import BrandLogo from "./BrandLogo";

interface BrandHeadingProps {
  /** Page name shown after the Sentinel wordmark, e.g. "Dashboard", "Admin Console". */
  label: string;
  /**
   * Replaces the "QA Intelligence Platform" tagline on the second line —
   * used by the sub-pages to put a "Back to dashboard" link there instead,
   * which is more useful than a tagline once you're already inside the app.
   */
  subtitle?: ReactNode;
}

/**
 * The Sentinel mark + wordmark, identical everywhere it appears.
 *
 * This exists because the dashboard, admin console and account page each had
 * their own copy of the header block, and only the dashboard's carried the
 * full branding — the other two rendered a bare, unglowed logo next to a
 * plain page title, so moving between them looked like moving between two
 * different products. One component means the mark can't drift again.
 */
export default function BrandHeading({ label, subtitle }: BrandHeadingProps) {
  return (
    <div className="flex items-center gap-3">
      <BrandLogo size={34} />
      <div>
        <h1 className="text-lg font-bold tracking-tight">
          <span className="text-cyan-400">Sentinel</span>{" "}
          <span className="font-normal text-slate-500 dark:text-white/60">{label}</span>
        </h1>
        {subtitle ?? (
          <p className="text-[10px] uppercase tracking-widest font-semibold text-slate-500 dark:text-white/25">
            QA Intelligence Platform
          </p>
        )}
      </div>
    </div>
  );
}
