"use client";

// /signup — events-app self-service signup. Creates an account with
// is_active=false. Admin approval is required before any auth-gated
// action will succeed (RSVP, check-in, post to chat, etc.).
//
// We still log the user in (issue a JWT) so they can see the "pending
// approval" screen with their email and stay signed in across reloads —
// AuthGate routes them to <PendingApproval/> until an admin flips
// is_active=true.

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/app/contexts/AuthContext";
import GoogleSignInButton from "@/components/GoogleSignInButton";

const eventsBrand = "#1d7a6c";

export default function SignupPage() {
  const { signup, user, loading: authLoading } = useAuth();
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // If they sign up successfully OR were already signed in, AuthGate
  // takes over (PendingApproval screen for is_active=false, app for
  // active users). Nothing to do here.
  useEffect(() => {
    if (!authLoading && user) router.replace("/");
  }, [user, authLoading, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (password.length < 6) {
      setError("Password must be at least 6 characters.");
      return;
    }
    setLoading(true);
    try {
      await signup(email, password, fullName || undefined);
    } catch (err: any) {
      setError(err.message || "Signup failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    // pb-28 reserves room for the mobile bottom nav so the form card
    // doesn't sit underneath it when the screen is short.
    <div className="min-h-[calc(100dvh-80px)] flex items-center justify-center bg-gray-50 px-4 py-8 pb-28 md:pb-8">
      <div className="max-w-md w-full">
        <div className="bg-white rounded-xl shadow-lg p-8">
          <div className="flex items-center justify-center mb-1">
            <div
              className="w-12 h-12 rounded-xl flex items-center justify-center"
              style={{ backgroundColor: eventsBrand }}
            >
              <span className="text-white font-bold text-lg">AH</span>
            </div>
          </div>
          <h1 className="text-2xl font-bold text-gray-900 text-center mt-3">
            Join Around Town
          </h1>
          <p className="text-sm text-gray-500 text-center mt-1 mb-6">
            New accounts are reviewed by an admin before they go live.
          </p>

          {/* Google Sign-In creates an active account immediately (email is
              verified by Google), so it's the faster path. Renders null when
              NEXT_PUBLIC_GOOGLE_OAUTH_CLIENT_ID is unset. */}
          <div className="mb-4 flex justify-center">
            <GoogleSignInButton onError={setError} />
          </div>
          <div className="flex items-center gap-2 mb-4 text-[10px] uppercase tracking-wider text-gray-400">
            <div className="flex-1 h-px bg-gray-200" />
            <span>or with email</span>
            <div className="flex-1 h-px bg-gray-200" />
          </div>

          <form onSubmit={handleSubmit} className="space-y-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                autoComplete="name"
                placeholder="What we should call you"
                className="block w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:ring-2 focus:border-transparent focus:ring-emerald-300"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
                className="block w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:ring-2 focus:border-transparent focus:ring-emerald-300"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={6}
                autoComplete="new-password"
                className="block w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:ring-2 focus:border-transparent focus:ring-emerald-300"
              />
              <p className="text-[10px] text-gray-400 mt-1">At least 6 characters.</p>
            </div>

            {error && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
                <p className="text-red-600 text-sm">{error}</p>
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full text-white py-2.5 rounded-lg hover:opacity-90 disabled:opacity-50 transition-colors font-medium"
              style={{ backgroundColor: eventsBrand }}
            >
              {loading ? "Creating account..." : "Request access"}
            </button>
          </form>

          <p className="text-center text-xs text-gray-500 mt-5">
            Already have an account?{" "}
            <Link href="/login" className="font-medium hover:underline" style={{ color: eventsBrand }}>
              Sign in
            </Link>
          </p>
        </div>

        <p className="text-center text-xs text-gray-400 mt-4">
          <Link href="/" className="hover:underline">← Keep browsing as a guest</Link>
        </p>
      </div>
    </div>
  );
}
