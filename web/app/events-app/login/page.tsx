"use client";

// /login — events-app sign-in page. Reuses the shared LoginForm which
// auto-detects the events.* subdomain and styles itself accordingly.
//
// On success the form leaves the user on this route; we redirect to /
// once the AuthContext flips to a logged-in user.

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import LoginForm from "@/components/LoginForm";
import { useAuth } from "@/app/contexts/AuthContext";

const eventsBrand = "#1d7a6c";

export default function LoginPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && user) router.replace("/");
  }, [user, loading, router]);

  return (
    <div className="min-h-screen flex flex-col">
      <LoginForm />
      <div className="px-4 pb-8 text-center">
        <p className="text-xs text-gray-500">
          Don&apos;t have an account?{" "}
          <Link href="/signup" className="font-medium hover:underline" style={{ color: eventsBrand }}>
            Create one
          </Link>
        </p>
        <p className="text-xs text-gray-400 mt-2">
          <Link href="/" className="hover:underline">← Keep browsing as a guest</Link>
        </p>
      </div>
    </div>
  );
}
