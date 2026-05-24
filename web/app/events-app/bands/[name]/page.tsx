"use client";

// /bands/[name] — every upcoming show for one band/act across all venues.
//
// The user's example: "Moroccan Sheepherders" plays at multiple spots —
// click their name on a calendar row and see every date + venue.
//
// Data: we don't have a `bands` table yet. We filter the cached calendar
// events by exact title (case-insensitive). Good enough at borough scale.
//
// "Find online" links open Facebook / Instagram / Google search in new
// tabs. We don't fetch / store band profiles ourselves yet — that needs
// a metadata table and either manual entry or scraping (deferred).

import { use, useMemo } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { getCalendarEvents, type CalendarEvent } from "@/lib/api";
import {
  ArrowLeftIcon, CalendarDaysIcon, MusicalNoteIcon,
  MapPinIcon,
} from "@heroicons/react/24/outline";

const eventsBrand = "#1d7a6c";

function fmtDate(iso: string): string {
  const d = new Date(iso + "T12:00:00");
  return d.toLocaleDateString(undefined, {
    weekday: "short", month: "short", day: "numeric",
  });
}

function externalLinks(bandName: string) {
  const q = encodeURIComponent(bandName);
  return [
    {
      label: "Facebook",
      href: `https://www.facebook.com/search/top?q=${q}`,
    },
    {
      label: "Instagram",
      href: `https://www.instagram.com/explore/search/keyword/?q=${q}`,
    },
    {
      label: "Bandsintown",
      href: `https://www.bandsintown.com/searchSuggestions?searchTerm=${q}&searchTab=artist`,
    },
    {
      label: "Google",
      // Bias toward NJ + band/music so we don't return random homonyms.
      href: `https://www.google.com/search?q=${q}+band+NJ+Atlantic+Highlands+OR+Sea+Bright`,
    },
  ];
}

export default function BandDetailPage({
  params,
}: {
  params: Promise<{ name: string }>;
}) {
  // Next 15: params is a Promise; React.use() unwraps it in a client component.
  const { name: nameParam } = use(params);
  const bandName = decodeURIComponent(nameParam);
  const todayIso = useMemo(() => new Date().toISOString().slice(0, 10), []);

  // Fetch this year's events (cached by react-query — shared with /calendar
  // so this is usually warm).
  const { data: events, isLoading } = useQuery({
    queryKey: ["all-events", new Date().getFullYear()],
    queryFn: () => getCalendarEvents(new Date().getFullYear()),
  });

  const shows = useMemo<CalendarEvent[]>(() => {
    const needle = bandName.trim().toLowerCase();
    return (events || [])
      .filter(e => e.event_type === "live_music" && (e.title || "").trim().toLowerCase() === needle)
      .filter(e => e.date >= todayIso)
      .sort((a, b) => a.date.localeCompare(b.date) || (a.time || "").localeCompare(b.time || ""));
  }, [events, bandName, todayIso]);

  const links = externalLinks(bandName);

  return (
    <div className="p-4 space-y-5">
      <Link
        href="/calendar"
        className="inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-900"
      >
        <ArrowLeftIcon className="w-3.5 h-3.5" /> Back to events
      </Link>

      <header>
        <div className="flex items-center gap-2 text-xs text-gray-500 uppercase tracking-wider">
          <MusicalNoteIcon className="w-3.5 h-3.5" />
          <span>Band / artist</span>
        </div>
        <h1 className="text-2xl font-bold text-gray-900 mt-0.5">{bandName}</h1>
        {!isLoading && (
          <p className="text-sm text-gray-600 mt-1">
            {shows.length === 0
              ? "No upcoming shows in the local listings."
              : `${shows.length} upcoming ${shows.length === 1 ? "show" : "shows"}`}
          </p>
        )}
      </header>

      {/* Find online — deep links to FB/IG/etc. since we don't store
          band profile URLs yet. */}
      <section>
        <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
          Find them online
        </div>
        <div className="flex flex-wrap gap-2">
          {links.map(l => (
            <a
              key={l.label}
              href={l.href}
              target="_blank"
              rel="noopener noreferrer"
              className="px-3 py-1.5 text-xs rounded-full border border-gray-300 text-gray-700 bg-white hover:bg-gray-50 hover:border-gray-400"
            >
              {l.label} ↗
            </a>
          ))}
        </div>
      </section>

      <section>
        <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
          Upcoming
        </div>
        {isLoading ? (
          <div className="text-sm text-gray-400">Loading…</div>
        ) : shows.length === 0 ? (
          <div className="bg-white border border-gray-200 rounded-lg p-6 text-center text-sm text-gray-400">
            Nothing scheduled locally for {bandName}. Check the links above.
          </div>
        ) : (
          <ul className="bg-white border border-gray-200 rounded-lg divide-y divide-gray-100 overflow-hidden">
            {shows.map(s => (
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
                  <div className="text-sm text-gray-900">
                    {fmtDate(s.date)}
                    {s.time && <span className="text-gray-500"> · {s.time}</span>}
                  </div>
                  <div className="text-[11px] text-gray-500 flex items-center gap-1 mt-0.5">
                    <MapPinIcon className="w-3 h-3 flex-shrink-0" />
                    {s.venue || s.location || "—"}
                    {s.city && <span className="text-gray-400"> · {s.city}</span>}
                  </div>
                </div>
                {s.ticket_url && (
                  <a
                    href={s.ticket_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs px-2 py-1 rounded border border-gray-300 text-gray-700 hover:bg-gray-50 flex-shrink-0"
                  >
                    Info ↗
                  </a>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
