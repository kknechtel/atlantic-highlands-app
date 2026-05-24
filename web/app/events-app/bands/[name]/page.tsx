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
import { findBandInGuide, socialMediaUrl, CATEGORY_LABELS } from "@/lib/bandGuide";
import {
  ArrowLeftIcon, CalendarDaysIcon, MusicalNoteIcon,
  MapPinIcon, StarIcon,
} from "@heroicons/react/24/outline";
import { StarIcon as StarSolid } from "@heroicons/react/24/solid";

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
  const guide = findBandInGuide(bandName);
  const social = socialMediaUrl(guide?.socialMedia);

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

      {/* Curated profile from the band guide — only shown when we have a match */}
      {guide && (
        <section
          className="bg-white border rounded-lg p-4"
          style={{ borderColor: `${eventsBrand}40` }}
        >
          <div className="flex items-center gap-2 mb-2">
            <div className="flex items-center gap-0.5">
              {[1, 2, 3, 4, 5].map(n => (
                n <= guide.rating
                  ? <StarSolid key={n} className="w-3.5 h-3.5" style={{ color: "#eab308" }} />
                  : <StarIcon key={n} className="w-3.5 h-3.5 text-gray-300" />
              ))}
            </div>
            <span className="text-[11px] text-gray-500">
              {CATEGORY_LABELS[guide.category]}
            </span>
          </div>
          <p className="text-sm text-gray-900 leading-snug">{guide.description}</p>
          {guide.vibe && (
            <p className="text-xs text-gray-600 mt-1 italic">{guide.vibe}</p>
          )}
          {guide.tags.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {guide.tags.map(t => (
                <span key={t} className="text-[10px] px-1.5 py-0.5 rounded-full bg-gray-100 text-gray-600">
                  {t}
                </span>
              ))}
            </div>
          )}
          <div className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-gray-500">
            {guide.regularVenues && (
              <div><span className="text-gray-400">Regulars at:</span> {guide.regularVenues}</div>
            )}
            {guide.reviews && (
              <div><span className="text-gray-400">Reviews:</span> {guide.reviews}</div>
            )}
            {social && (
              <div>
                <span className="text-gray-400">Social:</span>{" "}
                <a href={social.url} target="_blank" rel="noopener noreferrer"
                  className="hover:underline" style={{ color: eventsBrand }}>
                  {social.label} ↗
                </a>
              </div>
            )}
          </div>
        </section>
      )}

      {/* Find online — deep links to FB/IG/etc. since we don't store
          band profile URLs yet (or guide social didn't resolve to a URL). */}
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
