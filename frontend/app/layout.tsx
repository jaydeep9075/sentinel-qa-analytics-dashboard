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
  title: "Sentinel QA AI Analytics Dashboard",
  description: "Advanced QA Analytics with AI-powered insights",
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
        <Script id="strip-extension-injected-attrs" strategy="beforeInteractive">
          {`(function () {
  var strip = function (root) {
    if (!root || !root.querySelectorAll) return;
    var nodes = root.querySelectorAll('[bis_skin_checked]');
    for (var i = 0; i < nodes.length; i++) {
      nodes[i].removeAttribute('bis_skin_checked');
    }
  };
  strip(document);
  try {
    var observer = new MutationObserver(function (mutations) {
      for (var i = 0; i < mutations.length; i++) {
        var m = mutations[i];
        if (m.type === 'attributes' && m.attributeName === 'bis_skin_checked' && m.target && m.target.removeAttribute) {
          m.target.removeAttribute('bis_skin_checked');
        }
        if (m.addedNodes && m.addedNodes.length) {
          for (var j = 0; j < m.addedNodes.length; j++) {
            var n = m.addedNodes[j];
            if (n && n.nodeType === 1) strip(n);
          }
        }
      }
    });
    observer.observe(document.documentElement, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ['bis_skin_checked'],
    });
    window.addEventListener('load', function () {
      observer.disconnect();
    }, { once: true });
  } catch (_) {}
})();`}
        </Script>
        <ThemeInitializer />
        <ThemeToggle />
        {children}
      </body>
    </html>
  );
}
