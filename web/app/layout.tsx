import "./globals.css";
import type { Metadata } from "next";
import dynamic from "next/dynamic";

const Providers = dynamic(() => import("@/components/Providers"), { ssr: false });

export const metadata: Metadata = {
  title: "Atlantic Highlands",
  description: "Document Library & Financial Analysis",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-gray-50">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
