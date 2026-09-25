import { readFile } from "node:fs/promises";
import { join } from "node:path";

/**
 * Browser-tab favicon, served from the same public/tr-insight-logo.png the app
 * renders (see components/BrandLogo.tsx) so the two can never drift apart.
 */

export const contentType = "image/png";

export default async function Icon() {
  const png = await readFile(join(process.cwd(), "public", "tr-insight-logo.png"));
  return new Response(new Uint8Array(png), {
    headers: { "Content-Type": contentType },
  });
}
