import type { Metadata } from "next";
import { Geist, Geist_Mono, Inter } from "next/font/google";
import "./globals.css";
import { IngestionProvider } from "@/lib/IngestionContext";
import { RBProvider } from "@/lib/RBContext";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "Sentinel QA AI Analytics Dashboard",
  description: "Advanced QA Analytics with AI-powered insights",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body
        className={`${geistSans.variable} ${geistMono.variable} ${inter.variable} antialiased bg-[#0a0a0a] text-[#ededed]`}
      >
        <RBProvider>
          <IngestionProvider>{children}</IngestionProvider>
        </RBProvider>
      </body>
    </html>
  );
}
