"use client";

/**
 * The Testrig company logo, inlined from the official brand asset
 * (`public/testrig-logo.svg`, 329x49) so it scales without a network round
 * trip and recolours with the theme.
 *
 * Two colours, exactly as the brand file sets them:
 *   - the wordmark and the two chevrons stay Testrig green (#20BC75) in both
 *     themes, because that green is the logo;
 *   - the "i" glyphs, which the official file paints `black`, are drawn in
 *     `currentColor` instead. Painted black they disappear against the dark
 *     theme, which is the one bug you cannot ship on a logo.
 *
 * Sized by height only; the width follows the mark's own 6.71:1 ratio so it
 * can never squash.
 */

/** Intrinsic size of the official brand file. */
const LOGO_W = 329;
const LOGO_H = 49;

/**
 * Width-to-height ratio of the mark (6.71:1). Exported so a caller that has to
 * line something up underneath the logo can work out its rendered width from
 * the height it asked for, instead of measuring the DOM.
 */
export const TESTRIG_LOGO_RATIO = LOGO_W / LOGO_H;

/** Testrig brand green, taken from the official asset. */
export const TESTRIG_GREEN = "#20BC75";

interface TestrigLogoProps {
  /** Rendered height in px. 16 suits the app header, 24 the auth cards. */
  height?: number;
  className?: string;
}

export default function TestrigLogo({ height = 16, className = "" }: TestrigLogoProps) {
  return (
    <svg
      viewBox={`0 0 ${LOGO_W} ${LOGO_H}`}
      height={height}
      width={(height * LOGO_W) / LOGO_H}
      role="img"
      aria-label="Testrig"
      className={`shrink-0 select-none text-slate-900 dark:text-white ${className}`}
      style={{ height, width: "auto" }}
    >
      <path fillRule="evenodd" clipRule="evenodd" d="M19.8524 0.917969L27.6877 3.53679L10.0951 24.065L27.6877 44.572L19.8524 47.1909L0 24.065L19.8524 0.917969Z" fill="#20BC75" />
      <path fillRule="evenodd" clipRule="evenodd" d="M309.147 0.917969L301.291 3.53679L318.905 24.065L301.291 44.572L309.147 47.1909L329 24.065L309.147 0.917969Z" fill="#20BC75" />
      <path d="M33.8975 2.16406H70.7299V12.2381H58.5862V47.7189H45.9145V12.2381H33.8975V2.16406Z" fill="#20BC75" />
      <path d="M104.583 12.3014H88.1102V19.7355H102.662V29.366H88.1102V37.5815H104.583V47.7189H75.4385V2.16406H104.583V12.3014Z" fill="#20BC75" />
      <path d="M128.026 48.1633C117.889 48.1633 109.99 43.3269 109.483 33.5486H122.979C123.232 36.9699 125.239 38.1315 127.562 38.1315C129.885 38.1315 131.574 36.9699 131.574 34.8369C131.511 27.5295 109.42 30.9509 109.61 15.1324C109.61 6.21991 117.044 1.42578 126.675 1.42578C137.15 1.42578 143.993 6.53671 144.436 15.5759H130.666C130.54 12.7247 128.787 11.4364 126.464 11.4364C124.584 11.3731 123.105 12.4713 123.105 14.6677C123.105 21.4471 145.006 19.2507 145.006 33.8654C145.006 41.8697 138.797 48.1422 128.005 48.1422L128.026 48.1633Z" fill="#20BC75" />
      <path d="M148.364 2.16406H185.197V12.2381H173.053V47.7189H160.381V12.2381H148.364V2.16406Z" fill="#20BC75" />
      <path d="M209.886 2.16406C221.185 2.16406 226.887 8.62664 226.887 16.7788C226.887 22.7134 223.656 27.8876 216.877 29.9574L227.162 47.7189H213.012L203.973 30.9289H202.621V47.7189H189.949V2.16406H209.907H209.886ZM208.851 12.7661H202.579V22.2699H208.851C212.273 22.2699 214.025 20.6014 214.025 17.4968C214.025 14.6457 212.273 12.7872 208.851 12.7872V12.7661Z" fill="#20BC75" />
      <path d="M297.849 17.161H284.206C282.791 14.7745 280.193 13.4229 276.708 13.4229C270.309 13.4229 266.444 17.8791 266.444 24.8485C266.444 32.6628 270.457 36.8656 277.954 36.8656C282.347 36.8656 285.578 34.7958 287.458 30.8465H274.723V21.744H298.377V34.0144C295.674 40.6671 288.62 48.0378 276.729 48.0378C262.769 48.0378 253.604 38.4706 253.604 24.8485C253.604 11.2264 262.706 1.72266 276.666 1.72266C288.176 1.72266 296.054 7.65724 297.849 17.161Z" fill="#20BC75" />
      <path d="M254.195 2.39844H241.523L238.63 12.7681H251.302L254.195 2.39844Z" fill="currentColor" />
      <path d="M228.851 47.9532H241.522L250.435 15.8516H237.784L228.851 47.9532Z" fill="currentColor" />
    </svg>
  );
}
