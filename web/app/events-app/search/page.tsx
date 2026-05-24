"use client";

// /search — free-text event search.
//
// Type a query → debounced 250 ms → backend ILIKE search across
// title + venue + description. Two sections in the results:
//
//   Upcoming   — date >= today, what most people want
//   Earlier    — past matches, collapsed by default so a stale band
//                doesn't drown out their next show
//
// The query is mirrored to the URL (?q=...) so links + back/forward
// + bookmarks all work. Renders for anonymous users too — search is
// part of the public browse experience.

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  MagnifyingGlassIcon, XMarkIcon, MusicalNoteIcon, CalendarDaysIcon,
  ClockIcon, MapPinIcon,
} from "@heroicons/react/24/outline";
import { searchEvents, type CalendarEvent } from "@/lib/api";

const eventsBrand = "#1d7a6c";

function fmtDate(iso: string): string {
  const d = new Date(iso + "T12:00:00");
  return d.toLocaleDateString(undefined, {
    weekday: "short", month: "short", day: "numeric", year: "numeric",
  });
}

function EventRow({ ev }: { ev: CalendarEvent }) {
  const isMusic = ev.event_type === "live_music";
  return (
    <Link
      href={`/calendar/${ev.id}`}
      className="flex items-start gap-3 p-3 rounded-lg bg-white border border-gray-200 hover:shadow-sm hover:border-gray-300 transition"
    >
      <div className="w-12 text-center flex-shrink-0">
        <div className="text-[10px] text-gray-400 uppercase">
          {new Date(ev.date + "T12:00:00").toLocaleDateString(undefined, { weekday: "short" })}
        </div>
        <div className="text-lg font-bold text-gray-900 leading-none">
          {new Date(ev.date + "T12:00:00").getDate()}
        </div>
        <div className="text-[10px] text-gray-400">
          {new Date(ev.date + "T12:00:00").toLocaleDateString(undefined, { month: "short" })}
        </div>
      </div>
      <div
        className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
        style={{ backgroundColor: `${eventsBrand}15`, color: eventsBrand }}
      >
        {isMusic
          ? <MusicalNoteIcon className="w-4 h-4" />
          : <CalendarDaysIcon className="w-4 h-4" />}
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold text-gray-900 truncate">{ev.title}</div>
        <div className="text-[11px] text-gray-500 flex items-center gap-1.5 flex-wrap mt-0.5">
          <span>{fmtDate(ev.date)}</span>
          {ev.time && (
            <>
              <span className="text-gray-300">·</span>
              <ClockIcon className="w-3 h-3 inline -mt-0.5" />
              <span>{ev.time}</span>
            </>
          )}
          {ev.venue && (
            <>
              <span className="text-gray-300">·</span>
              <MapPinIcon className="w-3 h-3 inline -mt-0.5" />
              <span style={{ color: eventsBrand }}>{ev.venue}</span>
            </>
          )}
          {ev.city && (
            <span className="text-[9px] px-1 py-0.5 rounded bg-gray-100">{ev.city}</span>
          )}
        </div>
      </div>
    </Link>
  );
}

function SearchInner() {
  const router = useRouter();
  const sp = useSearchParams();
  const initialQ = (sp.get("q") || "").trim();

  // Input state is separate from the debounced query state so the input
  // feels instant while we wait to fire the API call.
  const [input, setInput] = useState(initialQ);
  const [debounced, setDebounced] = useState(initialQ);
  const [showPast, setShowPast] = useState(false);

  // Debounce input → debounced, and mirror to ?q= so links/back work.
  useEffect(() => {
    const t = window.setTimeout(() => {
      setDebounced(input.trim());
      const url = new URL(window.location.href);
      if (input.trim()) {
        url.searchParams.set("q", input.trim());
      } else {
        url.searchParams.delete("q");
      }
      window.history.replaceState({}, "", url.pathname + url.search);
    }, 250);
    return () => window.clearTimeout(t);
  }, [input]);

  const { data, isFetching } = useQuery({
    queryKey: ["event-search", debounced],
    queryFn: () => searchEvents(debounced, { limit: 200 }),
    enabled: debounced.length >= 2,
    staleTime: 60_000,
  });

  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);
  const upcoming = useMemo(() => (data || []).filter(e => e.date >= today), [data, today]);
  const past = useMemo(
    () => (data || []).filter(e => e.date < today).reverse(),  // most recent past first
    [data, today],
  );

  return (
    <div className="p-4 md:p-6 max-w-3xl mx-auto space-y-5">
      <div>
        <h1 className="text-xl md:text-2xl font-bold text-gray-900 flex items-center gap-2">
          <MagnifyingGlassIcon className="w-5 h-5" style={{ color: eventsBrand }} />
          Search events
        </h1>
        <p className="text-xs text-gray-500 mt-0.5">
          Find a band, an event, or a venue across every show in the calendar.
        </p>
      </div>

      <div className="relative">
        <MagnifyingGlassIcon className="w-5 h-5 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
        <input
          autoFocus
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") setInput("");
          }}
          placeholder="e.g. Brian Kirk, Proving Ground, karaoke"
          className="w-full pl-10 pr-10 py-3 text-base border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-300 focus:border-emerald-400"
        />
        {input && (
          <button
            onClick={() => setInput("")}
            className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 text-gray-400 hover:text-gray-700"
            title="Clear"
          >
            <XMarkIcon className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Empty / hint state */}
      {debounced.length < 2 && (
        <div className="bg-white border border-gray-200 rounded-lg p-6 text-center text-sm text-gray-500">
          Type at least 2 characters to search.
          <div className="mt-3 flex flex-wrap gap-2 justify-center">
            {["Brian Kirk", "Open Mic", "Sandbox", "karaoke"].map(s => (
              <button
                key={s}
                onClick={() => setInput(s)}
                className="text-xs px-2.5 py-1 rounded-full border border-gray-300 text-gray-700 hover:bg-gray-50"
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Loading */}
      {debounced.length >= 2 && isFetching && (
        <div className="text-sm text-gray-400">Searching…</div>
      )}

      {/* No results */}
      {debounced.length >= 2 && !isFetching && (data || []).length === 0 && (
        <div className="bg-white border border-gray-200 rounded-lg p-6 text-center text-sm text-gray-500">
          No events match <span className="font-medium text-gray-900">&ldquo;{debounced}&rdquo;</span>.
          <div className="text-xs text-gray-400 mt-1">
            Try a shorter query or check spelling.
          </div>
        </div>
      )}

      {/* Upcoming section */}
      {upcoming.length > 0 && (
        <section>
          <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
            Upcoming · {upcoming.length}
          </h2>
          <div className="space-y-2">
            {upcoming.map(ev => <EventRow key={ev.id} ev={ev} />)}
          </div>
        </section>
      )}

      {/* Past section (collapsed) */}
      {past.length > 0 && (
        <section>
          <button
            onClick={() => setShowPast(s => !s)}
            className="text-xs font-semibold text-gray-500 uppercase tracking-wider hover:text-gray-700"
          >
            {showPast ? "▾" : "▸"} Earlier · {past.length}
          </button>
          {showPast && (
            <div className="space-y-2 mt-2">
              {past.map(ev => <EventRow key={ev.id} ev={ev} />)}
            </div>
          )}
        </section>
      )}
    </div>
  );
}

export default function SearchPage() {
  // useSearchParams must be inside Suspense for the App Router.
  return (
    <Suspense fallback={<div className="p-4 text-sm text-gray-400">Loading…</div>}>
      <SearchInner />
    </Suspense>
  );
}
