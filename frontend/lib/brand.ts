// lib/brand.ts
//
// How the product introduces itself. One name and one line, imported by the
// landing footer, the sign-in card and the registration card — three places
// that had drifted into three different names for the same thing.

export const BRAND_NAME = "Testrig Sentinel";

/** The one-liner shown under the name. Keep it to a single sentence. */
export const BRAND_TAGLINE = "AI QE that knows your data";

/**
 * Whether to show the Testrig company logo in the brand lockup.
 *
 * White-labelling switch: a client who does not want the vendor's mark on
 * their dashboard gets `NEXT_PUBLIC_SHOW_TESTRIG_LOGO=false` in their build,
 * and the lockup renders the Sentinel mark and product name alone. Defaults
 * to showing it, so an unset variable behaves exactly as before.
 *
 * NEXT_PUBLIC_ variables are inlined by Next.js at BUILD time, not read at
 * container start - for Docker, pass it as a build arg (see frontend/Dockerfile
 * and the `build.args` block in docker-compose.yml), same as NEXT_PUBLIC_API_URL.
 */
export const SHOW_TESTRIG_LOGO = process.env.NEXT_PUBLIC_SHOW_TESTRIG_LOGO !== "false";
