"use client";

import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "@/app/contexts/AuthContext";
import Sidebar from "@/components/Sidebar";
import MobileNav from "@/components/MobileNav";
import GlobalChat from "@/components/GlobalChat";

export default function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());

  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        {/* Desktop layout */}
        <div className="hidden md:flex h-screen">
          <Sidebar />
          <main className="flex-1 overflow-auto">{children}</main>
        </div>
        {/* Mobile layout */}
        <div className="md:hidden flex flex-col h-screen">
          <main className="flex-1 overflow-auto pb-16">{children}</main>
          <MobileNav />
        </div>
        <GlobalChat />
      </AuthProvider>
    </QueryClientProvider>
  );
}
