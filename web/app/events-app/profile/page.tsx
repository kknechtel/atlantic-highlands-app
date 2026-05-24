"use client";

// /profile — edit display name (shown on chat + check-ins) and full name.
// Email/Google login + picture are read-only here; picture comes from
// Google and refreshes on every login.

import { useEffect, useState } from "react";
import Link from "next/link";
import { useMutation } from "@tanstack/react-query";
import { updateProfile } from "@/lib/api";
import { useAuth } from "@/app/contexts/AuthContext";
import {
  ArrowLeftIcon, ArrowRightOnRectangleIcon,
} from "@heroicons/react/24/outline";

const eventsBrand = "#1d7a6c";

export default function ProfilePage() {
  const { user, logout, setUser } = useAuth();
  const [displayName, setDisplayName] = useState("");
  const [fullName, setFullName] = useState("");
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Hydrate form when user lands or refreshes.
  useEffect(() => {
    if (!user) return;
    setDisplayName(user.display_name || "");
    setFullName(user.full_name || "");
  }, [user]);

  const save = useMutation({
    mutationFn: () => updateProfile({
      display_name: displayName.trim(),
      full_name: fullName.trim(),
    }),
    onSuccess: (u) => {
      setUser(u);
      setSaved(true);
      setErr(null);
      setTimeout(() => setSaved(false), 2000);
    },
    onError: (e: unknown) => setErr(e instanceof Error ? e.message : "Save failed"),
  });

  if (!user) {
    return <div className="p-4 text-sm text-gray-400">Loading…</div>;
  }

  const initial = (displayName || user.email || "?").trim().charAt(0).toUpperCase();

  return (
    <div className="p-4 space-y-5">
      <Link
        href="/"
        className="inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-900"
      >
        <ArrowLeftIcon className="w-3.5 h-3.5" /> Back
      </Link>

      <header className="flex items-center gap-3">
        {user.picture_url ? (
          /* eslint-disable-next-line @next/next/no-img-element */
          <img src={user.picture_url} alt="" className="w-14 h-14 rounded-full object-cover" />
        ) : (
          <div
            className="w-14 h-14 rounded-full flex items-center justify-center text-white text-xl font-bold"
            style={{ backgroundColor: eventsBrand }}
          >
            {initial}
          </div>
        )}
        <div className="min-w-0">
          <div className="text-lg font-semibold text-gray-900">
            {user.display_name || user.full_name || user.email.split("@")[0]}
          </div>
          <div className="text-xs text-gray-500 truncate">{user.email}</div>
        </div>
      </header>

      <section className="bg-white border border-gray-200 rounded-lg p-4 space-y-3">
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">
            Display name <span className="text-gray-400">(shown on chat & check-ins)</span>
          </label>
          <input
            value={displayName}
            onChange={e => setDisplayName(e.target.value.slice(0, 60))}
            placeholder={user.email.split("@")[0]}
            className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300 focus:border-emerald-400"
          />
          <div className="text-[10px] text-gray-400 mt-0.5">{displayName.length}/60</div>
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Full name</label>
          <input
            value={fullName}
            onChange={e => setFullName(e.target.value.slice(0, 120))}
            placeholder="Optional"
            className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300 focus:border-emerald-400"
          />
        </div>

        {err && <div className="text-xs text-red-700">{err}</div>}
        {saved && <div className="text-xs text-emerald-700">Saved ✓</div>}

        <div className="flex justify-end gap-2 pt-1">
          <button
            onClick={() => save.mutate()}
            disabled={save.isPending}
            className="px-3 py-1.5 text-sm rounded-md text-white disabled:opacity-50"
            style={{ backgroundColor: eventsBrand }}
          >
            {save.isPending ? "Saving…" : "Save"}
          </button>
        </div>
      </section>

      <section className="bg-white border border-gray-200 rounded-lg p-4 space-y-2">
        <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Account</div>
        <div className="text-xs text-gray-600">
          Signed in as {user.email}
          {user.picture_url && <span className="text-gray-400"> (Google)</span>}
        </div>
        <button
          onClick={logout}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md border border-gray-300 text-gray-700 hover:bg-gray-50"
        >
          <ArrowRightOnRectangleIcon className="w-4 h-4" /> Sign out
        </button>
      </section>
    </div>
  );
}
