import "./globals.css";
import type { Metadata, Viewport } from "next";
import Providers from "@/components/ProvidersClient";

export const metadata: Metadata = {
  title: "Atlantic Highlands",
  description: "Document Intelligence, Events & Local Business",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "AH Town",
  },
};

// Next 15: themeColor and viewport moved out of `metadata` into a
// separate `viewport` export.
export const viewport: Viewport = {
  themeColor: "#385854",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <link rel="apple-touch-icon" href="/icon-192.png" />
      </head>
      <body className="bg-gray-50">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
