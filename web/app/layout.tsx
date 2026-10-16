import { TOWN } from "@/lib/municipality";
import "./globals.css";
import type { Metadata, Viewport } from "next";
import Providers from "@/components/ProvidersClient";

export const metadata: Metadata = {
  title: TOWN.name,
  description: "Document Intelligence, Events & Local Business",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: `${TOWN.short_name} Town`,
  },
};

// Next 15: themeColor and viewport moved out of `metadata` into a
// separate `viewport` export. Pinch-zoom is left enabled (WCAG 1.4.4):
// users need to magnify dense tables and PDFs on small screens.
export const viewport: Viewport = {
  themeColor: TOWN.brand_color,
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" style={{ "--brand": TOWN.brand_color } as React.CSSProperties}>
      <head>
        <link rel="apple-touch-icon" href="/icon-192.png" />
      </head>
      <body className="bg-gray-50">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
