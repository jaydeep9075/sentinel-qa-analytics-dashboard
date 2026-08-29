import { ImageResponse } from "next/og";

/**
 * Browser-tab favicon, generated at build/request time instead of a static
 * PNG so the TR mark (see components/BrandLogo.tsx) never drifts from the
 * one actually shown in the app.
 */

export const size = { width: 32, height: 32 };
export const contentType = "image/png";

export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "transparent",
          color: "#20BC75",
          fontSize: 20,
          fontWeight: 800,
          letterSpacing: -0.5,
        }}
      >
        TR
      </div>
    ),
    { ...size },
  );
}
