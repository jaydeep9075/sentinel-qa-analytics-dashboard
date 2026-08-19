import type { Metadata } from "next";
import { Geist, Geist_Mono, Inter } from "next/font/google";
import Script from "next/script";
import "./globals.css";
import ThemeInitializer from "@/components/ThemeInitializer";
import ThemeToggle from "@/components/ThemeToggle";

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
  title: "Testrig Sentinel — QA AI Analytics Dashboard",
  description: "AI test analytics that answers your QA questions in plain English.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body
        suppressHydrationWarning
        className={`${geistSans.variable} ${geistMono.variable} ${inter.variable} antialiased`}
      >
        <Script id="strip-bis-attrs" strategy="beforeInteractive">
          {`
            (function () {
              var strip = function () {
                var nodes = document.querySelectorAll('[bis_skin_checked]');
                for (var i = 0; i < nodes.length; i++) {
                  nodes[i].removeAttribute('bis_skin_checked');
                }
              };
              strip();
              var observer = new MutationObserver(function () {
                strip();
              });
              observer.observe(document.documentElement, {
                childList: true,
                subtree: true,
                attributes: true,
                attributeFilter: ['bis_skin_checked']
              });
              window.addEventListener('load', function () {
                setTimeout(function () {
                  observer.disconnect();
                }, 1500);
              });
            })();
          `}
        </Script>
        <ThemeInitializer />
        <ThemeToggle />
        {children}
      </body>
    </html>
  );
}
