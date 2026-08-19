"use client";

/**
 * The company name, set the way the Testrig mark sets it: angle brackets
 * around the name, and the "i" lowercase and green.
 *
 * This is type, not the logo image. The header already carries one mark (the
 * Sentinel cube) and adding a second tile beside it would be two logos
 * competing in a 44px-tall bar — so the company name is drawn in the brand's
 * own lettering instead, which scales, recolours with the theme and costs no
 * request.
 */
export default function TestrigWordmark({ className = "" }: { className?: string }) {
  return (
    <span
      className={`select-none font-bold uppercase tracking-tight text-slate-600 dark:text-white/70 ${className}`}
      aria-label="Testrig"
    >
      <span className="font-normal text-slate-400 dark:text-white/35" aria-hidden>
        &lt;
      </span>
      <span aria-hidden>
        TESTR<span className="lowercase italic text-emerald-500">i</span>G
      </span>
      <span className="font-normal text-slate-400 dark:text-white/35" aria-hidden>
        &gt;
      </span>
    </span>
  );
}
