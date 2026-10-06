import type { Metadata, Viewport } from "next";
import "leaflet/dist/leaflet.css";
import "./globals.css";
import { SiteHeader } from "@/components/SiteHeader";

export const metadata: Metadata = {
  title: "NadiNet — Jamuna riverbank watch",
  description:
    "Free Sentinel-1 radar maps the Jamuna's banks through monsoon cloud after every pass and ranks 200 m segments by 28-day erosion risk, tested against what actually happened.",
  icons: { icon: "/logo.svg" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f9f9f7" },
    { media: "(prefers-color-scheme: dark)", color: "#0d0d0d" },
  ],
};

// Applies the stored or system theme before paint (no flash).
const themeScript = `(function(){try{var t=localStorage.getItem('nadinet.theme');var d=t?t==='dark':window.matchMedia('(prefers-color-scheme: dark)').matches;if(d)document.documentElement.classList.add('dark');}catch(e){}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="min-h-screen">
        <SiteHeader />
        <main>{children}</main>
        <footer className="mt-16 border-t py-8 text-xs text-muted-foreground">
          <div className="container flex flex-col gap-2 sm:flex-row sm:justify-between">
            <p>
              NadiNet v3.0 · Advisory decision support. The absence of an alert does not mean a bank is safe.
            </p>
            <p>
              Contains modified Copernicus Sentinel data (2015–2025), processed by NadiNet. MIT-licensed code.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
