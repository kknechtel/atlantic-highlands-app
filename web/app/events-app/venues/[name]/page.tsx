"use client";

// /venues/[name] — everything on at one venue, the counterpart to
// /bands/[name].
//
// Clicking a venue in any event row lands here: what's coming up, who's
// there right now, and a way to check in. Acts link on to their own
// pages, so you can bounce venue → band → another venue.
//
// Data: like the band page, we filter the cached calendar events by
// venue name rather than hitting a dedicated endpoint. There's no
// `venues` table — the venue string is written by the scrapers, and the
// registry is the closest thing to a canonical list.

import { use, useMemo, useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeftIcon, MapPinIcon, MusicalNoteIcon, UserGroupIcon,
  CalendarDaysIcon, XMarkIcon,
} from "@heroicons/react/24/outline";

import {
  getCalendarEvents, listCheckinsAtVenue, createCheckin,
  type CalendarEvent,
} from "@/lib/api";
import { bandHref, eventHref } from "@/lib/eventLinks";
import { useAuth } from "@/app/contexts/AuthContext";

const eventsBrand = "#1d7a6c";

function fmtDate(iso: string): string {
  return new Date(iso + "T12:00:00").toLocaleDateString(undefined, {
    weekday: "short", month: "short", day: "numeric",
  });
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

export default function VenueDetailPage({
  params,
}: {
  params: Promise<{ name: string }>;
}) {
  const { name: nameParam } = use(params);
  const venueName = decodeURIComponent(nameParam);
  const todayIso = useMemo(() => new Date().toISOString().slice(0, 10), []);
  const { user } = useAuth();
  const qc = useQueryClient();

  // Shares the ["all-events", year] cache with /calendar and /bands, so
  // arriving from a row is usually instant.
  const { data: events, isLoading } = useQuery({
    queryKey: ["all-events", new Date().getFullYear()],
    queryFn: () => getCalendarEvents(new Date().getFullYear()),
  });

  const shows = useMemo<CalendarEvent[]>(() => {
    const needle = venueName.trim().toLowerCase();
    return (events || [])
      .filter(e => (e.venue || "").trim().toLowerCase() === needle)
      .filter(e => e.date >= todayIso);
      // Already ordered by date then time by the API.
  }, [events, venueName, todayIso]);

  const city = shows.find(s => s.city)?.city || null;

  const { data: hereNow } = useQuery({
    queryKey: ["checkins-at", venueName],
    queryFn: () => listCheckinsAtVenue(venueName),
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  });

  const myActive = useMemo(
    () => (hereNow || []).find(c => c.user_id === user?.id) || null,
    [hereNow, user?.id],
  );

  const [showCheckin, setShowCheckin] = useState(false);
  const [message, setMessage] = useState("");
  const create = useMutation({
    mutationFn: () => createCheckin({
      venue_name: venueName,
      city: city || undefined,
      message: message.trim() || undefined,
    }),
    onSuccess: () => {
      setShowCheckin(false);
      setMessage("");
      qc.invalidateQueries({ queryKey: ["checkins-at", venueName] });
      qc.invalidateQueries({ queryKey: ["checkins-active"] });
    },
  });

  return (
    <div className="p-4 space-y-5">
      <Link href="/calendar" className="inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-900">
        <ArrowLeftIcon className="w-3.5 h-3.5" /> Back to events
      </Link>

      <header>
        <div className="flex items-center gap-2 text-xs text-gray-500 uppercase tracking-wider">
          <MapPinIcon className="w-3.5 h-3.5" />
          <span>Venue</span>
          {city && (
            <>
              <span className="text-gray-300">·</span>
              <span>{city}</span>
            </>
          )}
        </div>
        <h1 className="text-2xl font-bold text-gray-900 mt-0.5">{venueName}</h1>
        {!isLoading && (
          <p className="text-sm text-gray-600 mt-1">
            {shows.length === 0
              ? "Nothing listed here right now."
              : `${shows.length} upcoming ${shows.length === 1 ? "event" : "events"}`}
          </p>
        )}
      </header>

      {/* Check in / who's here */}
      <section className="bg-white border border-gray-200 rounded-lg p-3">
        {!user ? (
          <div className="text-[11px] text-gray-500">
            <Link href="/login" className="hover:underline font-medium" style={{ color: eventsBrand }}>
              Sign in
            </Link>{" "}
            to check in here.
          </div>
        ) : myActive ? (
          <div className="text-sm text-gray-700">You&apos;re checked in here.</div>
        ) : (
          <button
            onClick={() => setShowCheckin(true)}
            className="w-full px-3 py-2 text-sm rounded-md text-white"
            style={{ backgroundColor: eventsBrand }}
          >
            <MapPinIcon className="w-4 h-4 inline mr-1 -mt-0.5" />
            Check in at {venueName}
          </button>
        )}

        {hereNow && hereNow.length > 0 && (
          <div className="mt-3">
            <div className="text-[11px] uppercase tracking-wider text-gray-500 flex items-center gap-1 mb-1.5">
              <UserGroupIcon className="w-3 h-3" /> Here now ({hereNow.length})
            </div>
            <div className="flex items-center gap-1.5 flex-wrap">
              {hereNow.slice(0, 12).map(c => (
                <div key={c.id} className="flex items-center gap-1 text-[11px] text-gray-600">
                  <Avatar name={c.user_display_name} src={c.user_picture_url} />
                  <span className="max-w-[80px] truncate">{c.user_display_name || "Someone"}</span>
                </div>
              ))}
              {hereNow.length > 12 && (
                <span className="text-[11px] text-gray-400">+{hereNow.length - 12} more</span>
              )}
            </div>
          </div>
        )}
      </section>

      {/* Upcoming — act names link on to their own pages */}
      <section>
        <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
          Upcoming
        </div>
        {isLoading ? (
          <div className="text-sm text-gray-400">Loading…</div>
        ) : shows.length === 0 ? (
          <div className="bg-white border border-gray-200 rounded-lg p-6 text-center text-sm text-gray-400">
            Nothing scheduled at {venueName} in the current listings.
          </div>
        ) : (
          <ul className="bg-white border border-gray-200 rounded-lg divide-y divide-gray-100 overflow-hidden">
            {shows.map(s => {
              const band = bandHref(s);
              return (
                <li key={s.id} className="px-3 py-2.5 flex items-center gap-3">
                  <div className="w-12 text-center flex-shrink-0">
                    <div className="text-[9px] uppercase text-gray-400">
                      {new Date(s.date + "T12:00:00").toLocaleDateString("en-US", { month: "short" })}
                    </div>
                    <div className="text-base font-bold text-gray-900 leading-none">
                      {new Date(s.date + "T12:00:00").getDate()}
                    </div>
                  </div>
                  <div className="flex-1 min-w-0">
                    {band ? (
                      <Link href={band} className="text-sm font-semibold text-gray-900 hover:underline block truncate">
                        {s.title}
                      </Link>
                    ) : (
                      <div className="text-sm font-semibold text-gray-900 truncate">{s.title}</div>
                    )}
                    <div className="text-[11px] text-gray-500 flex items-center gap-1.5 flex-wrap mt-0.5">
                      <span>{fmtDate(s.date)}</span>
                      {s.time && (
                        <>
                          <span className="text-gray-300">·</span>
                          <span>{s.time}{s.end_time ? `–${s.end_time}` : ""}</span>
                        </>
                      )}
                      {s.event_type === "live_music" && (
                        <MusicalNoteIcon className="w-3 h-3 text-gray-400" />
                      )}
                    </div>
                  </div>
                  <Link
                    href={eventHref(s.id)}
                    className="text-xs px-2 py-1 rounded border border-gray-300 text-gray-700 hover:bg-gray-50 flex-shrink-0"
                  >
                    Details
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {/* Check-in modal */}
      {showCheckin && (
        <div
          className="fixed inset-0 bg-black/40 z-50 flex items-end sm:items-center justify-center p-4"
          onClick={() => setShowCheckin(false)}
        >
          <div className="bg-white rounded-xl w-full max-w-sm p-4 shadow-xl" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-1">
              <div className="text-base font-semibold text-gray-900">Check in at {venueName}</div>
              <button onClick={() => setShowCheckin(false)} className="p-1 hover:bg-gray-100 rounded">
                <XMarkIcon className="w-4 h-4 text-gray-400" />
              </button>
            </div>
            {city && <div className="text-xs text-gray-500 mb-3">{city}</div>}
            <textarea
              value={message}
              onChange={e => setMessage(e.target.value.slice(0, 200))}
              placeholder="Optional note (where to find you, etc.)"
              rows={2}
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300 focus:border-emerald-400"
            />
            <div className="flex justify-end gap-2 mt-3">
              <button onClick={() => setShowCheckin(false)} className="px-3 py-1.5 text-sm rounded-md text-gray-600 hover:bg-gray-50">
                Cancel
              </button>
              <button
                onClick={() => create.mutate()}
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

      <p className="text-[10px] text-gray-400 flex items-center gap-1">
        <CalendarDaysIcon className="w-3 h-3" />
        Listings come from {venueName}&apos;s own schedule, refreshed nightly.
      </p>
    </div>
  );
}
