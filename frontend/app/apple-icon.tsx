import { ImageResponse } from "next/og";

/** iOS home-screen icon — same TR mark as icon.tsx, at Apple's touch-icon size. */

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#20BC75",
          borderRadius: 40,
          color: "#ffffff",
          fontSize: 96,
          fontWeight: 800,
          letterSpacing: -3,
        }}
      >
        TR
      </div>
    ),
    { ...size },
  );
}
