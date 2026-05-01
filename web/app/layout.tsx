import "./globals.css";
import type { Metadata } from "next";
import dynamic from "next/dynamic";

const Providers = dynamic(() => import("@/components/Providers"), { ssr: false });

export const metadata: Metadata = {
  title: "Atlantic Highlands",
  description: "Document Intelligence, Events & Local Business",
  manifest: "/manifest.json",
  themeColor: "#385854",
  viewport: {
    width: "device-width",
    initialScale: 1,
    maximumScale: 1,
    userScalable: false,
  },
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "AH Town",
  },
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
