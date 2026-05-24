"use client";

// /checkin — "I'm out at X right now". Three sections:
//   1. Your active check-in (if any) + quick undo
//   2. Live "who's where" board — venues with active check-ins, names/avatars
//   3. Quick-check-in chooser — known venues + free-text fallback
//
// All check-ins expire server-side after 4 hours. Refetches every 60s so
// the board feels live without WebSocket overhead at borough scale.

import { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  MapPinIcon, UserGroupIcon, PlusIcon, XMarkIcon,
} from "@heroicons/react/24/outline";
import {
  listActiveCheckins, listCheckinVenues, createCheckin, deleteCheckin,
  getCalendarEvents,
  type Checkin,
} from "@/lib/api";
import { useAuth } from "@/app/contexts/AuthContext";

const eventsBrand = "#1d7a6c";

// Known venues we'll always offer in the picker. Derived from the live-music
// scraper registry + a few well-known SB/AH spots. Free text is still
// allowed as a fallback so users can check in anywhere.
const KNOWN_VENUES: { name: string; city: string }[] = [
  { name: "The Proving Ground", city: "Highlands" },
  { name: "The Chubby Pickle", city: "Highlands" },
  { name: "The Seafarer", city: "Highlands" },
  { name: "The Sandbox at Seastreak", city: "Highlands" },
  { name: "Off the Hook", city: "Highlands" },
  { name: "Bahrs Landing", city: "Highlands" },
  { name: "Inlet Cafe", city: "Highlands" },
  { name: "One Willow", city: "Highlands" },
  { name: "Mule Barn Tavern", city: "Highlands" },
  { name: "On the Deck", city: "Atlantic Highlands" },
  { name: "Gaslight Gastropub", city: "Atlantic Highlands" },
  { name: "Carton Brewing", city: "Atlantic Highlands" },
  { name: "Copper Canyon", city: "Atlantic Highlands" },
  { name: "The Wine Bar", city: "Atlantic Highlands" },
  { name: "Atlantic House", city: "Atlantic Highlands" },
  { name: "Smodcastle Cinemas", city: "Atlantic Highlands" },
  { name: "First Ave Playhouse", city: "Atlantic Highlands" },
  { name: "Donovan's Reef", city: "Sea Bright" },
  { name: "Drifthouse by David Burke", city: "Sea Bright" },
  { name: "McLoone's Rum Runner", city: "Sea Bright" },
  { name: "Tommy's Tavern + Tap", city: "Sea Bright" },
  { name: "Eventide Grille", city: "Sea Bright" },
];

function fmtAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diffMs / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  return `${h}h ago`;
}

function Avatar({ name, src }: { name: string | null; src: string | null }) {
  const letter = (name || "?").trim().charAt(0).toUpperCase();
  return src ? (
    /* eslint-disable-next-line @next/next/no-img-element */
    <img src={src} alt={name || ""} className="w-7 h-7 rounded-full object-cover" />
  ) : (
    <div
      className="w-7 h-7 rounded-full flex items-center justify-center text-white text-xs font-semibold"
      style={{ backgroundColor: eventsBrand }}
    >
      {letter}
    </div>
  );
}

export default function CheckinPage() {
  const { user } = useAuth();
  const qc = useQueryClient();

  const { data: active } = useQuery({
    queryKey: ["checkins-active"],
    queryFn: () => listActiveCheckins(100),
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  });

  const { data: venues } = useQuery({
    queryKey: ["checkin-venues"],
    queryFn: listCheckinVenues,
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  });

  // Pull current calendar events so we can tag a check-in with "X is playing tonight".
  const { data: events } = useQuery({
    queryKey: ["checkin-events-today"],
    queryFn: () => getCalendarEvents(new Date().getFullYear()),
  });

  const myActive = useMemo(
    () => (active || []).filter(c => c.user_id === user?.id),
    [active, user?.id],
  );

  const checkinsByVenue = useMemo(() => {
    const m = new Map<string, Checkin[]>();
    for (const c of active || []) {
      const list = m.get(c.venue_name) || [];
      list.push(c);
      m.set(c.venue_name, list);
    }
    return m;
  }, [active]);

  // ── Mutations ─────────────────────────────────────────────────
  const create = useMutation({
    mutationFn: (p: { venue_name: string; city?: string; message?: string }) =>
      createCheckin(p),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["checkins-active"] });
      qc.invalidateQueries({ queryKey: ["checkin-venues"] });
    },
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteCheckin(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["checkins-active"] });
      qc.invalidateQueries({ queryKey: ["checkin-venues"] });
    },
  });

  // ── Modal state ───────────────────────────────────────────────
  const [pickerVenue, setPickerVenue] = useState<{ name: string; city: string } | null>(null);
  const [customName, setCustomName] = useState("");
  const [customCity, setCustomCity] = useState("");
  const [message, setMessage] = useState("");

  function openModal(v: { name: string; city: string }) {
    setPickerVenue(v);
    setMessage("");
  }
  function submit() {
    if (!pickerVenue) return;
    create.mutate({
      venue_name: pickerVenue.name,
      city: pickerVenue.city,
      message: message.trim() || undefined,
    });
    setPickerVenue(null);
  }
  function submitCustom() {
    if (!customName.trim()) return;
    create.mutate({
      venue_name: customName.trim(),
      city: customCity.trim() || undefined,
      message: message.trim() || undefined,
    });
    setCustomName("");
    setCustomCity("");
    setMessage("");
  }

  // Today's live-music events to show as "What's on" tags
  const tonight = useMemo(() => {
    const today = new Date().toISOString().slice(0, 10);
    return (events || []).filter(e => e.event_type === "live_music" && e.date === today);
  }, [events]);

  return (
    <div className="p-4 space-y-6">
      <div>
        <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
          <MapPinIcon className="w-5 h-5" style={{ color: eventsBrand }} />
          Check in
        </h1>
        <p className="text-xs text-gray-500 mt-0.5">
          Let people know where you are. Check-ins clear after 4 hours.
        </p>
      </div>

      {/* Your active check-ins */}
      {myActive.length > 0 && (
        <section>
          <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
            You&apos;re checked in
          </h2>
          <ul className="space-y-2">
            {myActive.map(c => (
              <li
                key={c.id}
                className="bg-white border rounded-lg p-3 flex items-start justify-between gap-2"
                style={{ borderColor: eventsBrand }}
              >
                <div className="min-w-0">
                  <div className="text-sm font-semibold text-gray-900">{c.venue_name}</div>
                  <div className="text-[11px] text-gray-500">
                    {c.city ? `${c.city} · ` : ""}{fmtAgo(c.checked_in_at)}
                  </div>
                  {c.message && (
                    <div className="text-xs text-gray-700 mt-1">{c.message}</div>
                  )}
                </div>
                <button
                  onClick={() => remove.mutate(c.id)}
                  className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded"
                  title="Check out"
                >
                  <XMarkIcon className="w-4 h-4" />
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Who's where right now */}
      <section>
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 flex items-center gap-1.5">
          <UserGroupIcon className="w-3.5 h-3.5" /> Who&apos;s out tonight
        </h2>
        {!venues || venues.length === 0 ? (
          <div className="bg-white border border-gray-200 rounded-lg p-6 text-center text-sm text-gray-400">
            Nobody&apos;s checked in yet. Be first.
          </div>
        ) : (
          <ul className="space-y-2">
            {venues.map(v => {
              const list = checkinsByVenue.get(v.venue_name) || [];
              return (
                <li key={v.venue_name} className="bg-white border border-gray-200 rounded-lg p-3">
                  <div className="flex items-center justify-between mb-1.5">
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-gray-900 truncate">{v.venue_name}</div>
                      <div className="text-[11px] text-gray-500">
                        {v.city ? `${v.city} · ` : ""}{v.active_count} here
                      </div>
                    </div>
                    <button
                      onClick={() => openModal({ name: v.venue_name, city: v.city || "" })}
                      className="px-2.5 py-1 text-xs rounded-md text-white"
                      style={{ backgroundColor: eventsBrand }}
                    >
                      Join
                    </button>
                  </div>
                  <div className="flex items-center gap-1.5 mt-2 flex-wrap">
                    {list.slice(0, 12).map(c => (
                      <div key={c.id} className="flex items-center gap-1 text-[11px] text-gray-600">
                        <Avatar name={c.user_display_name} src={c.user_picture_url} />
                        <span className="max-w-[80px] truncate">{c.user_display_name || "Someone"}</span>
                      </div>
                    ))}
                    {list.length > 12 && (
                      <span className="text-[11px] text-gray-400">+{list.length - 12} more</span>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {/* Quick check-in: tonight's music venues + known venue chooser */}
      {tonight.length > 0 && (
        <section>
          <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
            Live music tonight
          </h2>
          <ul className="space-y-2">
            {tonight.map(e => (
              <li key={e.id} className="bg-white border border-gray-200 rounded-lg p-3 flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <div className="text-sm text-gray-900 truncate">{e.title}</div>
                  <div className="text-[11px] text-gray-500">
                    {e.time && <span>{e.time} · </span>}
                    {e.venue}{e.city ? ` · ${e.city}` : ""}
                  </div>
                </div>
                <button
                  onClick={() => e.venue && openModal({ name: e.venue, city: e.city || "" })}
                  disabled={!e.venue}
                  className="px-2.5 py-1 text-xs rounded-md border border-gray-300 text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                >
                  Check in
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
          Pick a spot
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {KNOWN_VENUES.map(v => (
            <button
              key={v.name}
              onClick={() => openModal(v)}
              className="bg-white border border-gray-200 rounded-lg p-3 text-left hover:border-gray-300 flex items-start justify-between gap-2"
            >
              <div className="min-w-0">
                <div className="text-sm font-medium text-gray-900 truncate">{v.name}</div>
                <div className="text-[11px] text-gray-500">{v.city}</div>
              </div>
              <PlusIcon className="w-4 h-4 text-gray-400 flex-shrink-0 mt-1" />
            </button>
          ))}
        </div>
      </section>

      {/* Free-text fallback */}
      <section className="bg-white border border-gray-200 rounded-lg p-3">
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
          Somewhere else
        </h2>
        <div className="space-y-2">
          <input
            value={customName}
            onChange={e => setCustomName(e.target.value)}
            placeholder="Venue name"
            className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300 focus:border-emerald-400"
          />
          <input
            value={customCity}
            onChange={e => setCustomCity(e.target.value)}
            placeholder="City (optional)"
            className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300 focus:border-emerald-400"
          />
          <button
            onClick={submitCustom}
            disabled={!customName.trim() || create.isPending}
            className="w-full px-3 py-2 text-sm rounded-md text-white disabled:opacity-50"
            style={{ backgroundColor: eventsBrand }}
          >
            Check in
          </button>
        </div>
      </section>

      {/* Modal for picking a known venue */}
      {pickerVenue && (
        <div
          className="fixed inset-0 bg-black/40 z-50 flex items-end sm:items-center justify-center p-4"
          onClick={() => setPickerVenue(null)}
        >
          <div
            className="bg-white rounded-xl w-full max-w-sm p-4 shadow-xl"
            onClick={e => e.stopPropagation()}
          >
            <div className="text-base font-semibold text-gray-900 mb-1">
              Check in at {pickerVenue.name}
            </div>
            <div className="text-xs text-gray-500 mb-3">{pickerVenue.city}</div>
            <textarea
              value={message}
              onChange={e => setMessage(e.target.value.slice(0, 200))}
              placeholder="Optional note (where to find you, etc.)"
              rows={2}
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300 focus:border-emerald-400"
            />
            <div className="flex justify-end gap-2 mt-3">
              <button
                onClick={() => setPickerVenue(null)}
                className="px-3 py-1.5 text-sm rounded-md text-gray-600 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={submit}
                disabled={create.isPending}
                className="px-3 py-1.5 text-sm rounded-md text-white disabled:opacity-50"
                style={{ backgroundColor: eventsBrand }}
              >
                {create.isPending ? "Checking in…" : "Check in"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
