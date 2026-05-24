"use client";

// /admin/event-ingest — drag-drop a venue's monthly calendar image,
// Claude Vision parses the events, admin reviews and commits.
//
// Flow:
//   1. Pick venue + drop image → POST /api/event-ingest/parse
//   2. Render returned rows in an editable grid (date / time / title)
//      so the admin can fix OCR misreads before they hit the calendar
//   3. Commit → POST /api/event-ingest/commit; show inserted/skipped
//
// Only admins can reach this — non-admins see a 403 message instead
// of the form. We never wedge the page on auth errors; the API itself
// also gates with get_admin_user.

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/app/contexts/AuthContext";
import {
  parseCalendarImage, commitIngestedEvents,
  type ParsedIngestEvent,
} from "@/lib/api";
import {
  ArrowUpTrayIcon, PhotoIcon, TrashIcon, PlusIcon, CheckIcon, XMarkIcon,
} from "@heroicons/react/24/outline";

const eventsBrand = "#1d7a6c";

const KNOWN_VENUES = [
  // Sandbox first — its full season lives on Bandsintown (blocked from
  // our EC2 IPs), so this tool is the primary way to get it in.
  { name: "The Sandbox at Seastreak", city: "Highlands" },
  { name: "Gaslight Gastropub", city: "Atlantic Highlands" },
  { name: "McLoone's Rum Runner", city: "Sea Bright" },
  { name: "Tommy's Tavern + Tap", city: "Sea Bright" },
  { name: "Eventide Grille", city: "Sea Bright" },
  { name: "Wine Bar", city: "Atlantic Highlands" },
  { name: "Atlantic House", city: "Atlantic Highlands" },
  { name: "Copper Canyon", city: "Atlantic Highlands" },
  { name: "Carton Brewing", city: "Atlantic Highlands" },
  { name: "Off the Hook", city: "Highlands" },
  { name: "Bahrs Landing", city: "Highlands" },
  { name: "Inlet Cafe", city: "Highlands" },
  { name: "One Willow", city: "Highlands" },
  { name: "Mule Barn Tavern", city: "Highlands" },
];

export default function EventIngestPage() {
  const { user } = useAuth();

  const [venue, setVenue] = useState("The Sandbox at Seastreak");
  const [city, setCity] = useState("Highlands");
  const [hintMonth, setHintMonth] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const [parsing, setParsing] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notes, setNotes] = useState<string>("");
  const [events, setEvents] = useState<ParsedIngestEvent[]>([]);
  const [committed, setCommitted] = useState<{ inserted: number; skipped: number } | null>(null);

  useEffect(() => {
    if (!file) { setPreview(null); return; }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  // Default the month hint to "Month YYYY" of today — most uploads are
  // for the current month so this saves a click.
  const todayMonthHint = useMemo(
    () => new Date().toLocaleDateString(undefined, { month: "long", year: "numeric" }),
    [],
  );
  useEffect(() => { if (!hintMonth) setHintMonth(todayMonthHint); }, [todayMonthHint, hintMonth]);

  if (!user) {
    return (
      <div className="p-6">
        <Link href="/" className="text-xs text-gray-500 hover:underline">← Home</Link>
        <h1 className="text-lg font-semibold text-gray-900 mt-3">Sign in required</h1>
      </div>
    );
  }
  if (!user.is_admin) {
    return (
      <div className="p-6">
        <Link href="/" className="text-xs text-gray-500 hover:underline">← Home</Link>
        <h1 className="text-lg font-semibold text-gray-900 mt-3">Admin only</h1>
        <p className="text-sm text-gray-500 mt-1">
          The calendar image ingest tool is restricted to admin accounts.
        </p>
      </div>
    );
  }

  function pickFile(f: File | null) {
    setFile(f);
    setEvents([]);
    setCommitted(null);
    setError(null);
    setNotes("");
  }

  async function onParse() {
    if (!file) { setError("Pick an image first."); return; }
    if (!venue.trim()) { setError("Pick a venue."); return; }
    setError(null);
    setCommitted(null);
    setParsing(true);
    try {
      const res = await parseCalendarImage({
        file, venue: venue.trim(), city: city.trim() || undefined,
        hint_month: hintMonth.trim() || undefined,
      });
      setEvents(res.events);
      setNotes(res.notes || "");
      if (res.events.length === 0) {
        setError(res.notes || "Claude returned no events from this image.");
      }
    } catch (err: any) {
      setError(err.message || "parse failed");
    } finally {
      setParsing(false);
    }
  }

  async function onCommit() {
    if (events.length === 0) return;
    if (!venue.trim()) { setError("Pick a venue."); return; }
    setError(null);
    setCommitting(true);
    try {
      const res = await commitIngestedEvents({
        venue: venue.trim(),
        city: city.trim() || undefined,
        events,
      });
      setCommitted({ inserted: res.inserted, skipped: res.skipped });
      if (res.inserted > 0) {
        // Leave events on screen so the admin can confirm what was sent,
        // but clear the file so we don't accidentally double-submit.
        setFile(null);
      }
    } catch (err: any) {
      setError(err.message || "commit failed");
    } finally {
      setCommitting(false);
    }
  }

  function updateEvent(i: number, patch: Partial<ParsedIngestEvent>) {
    setEvents(prev => prev.map((e, idx) => idx === i ? { ...e, ...patch } : e));
  }
  function removeEvent(i: number) {
    setEvents(prev => prev.filter((_, idx) => idx !== i));
  }
  function addBlankEvent() {
    setEvents(prev => [
      ...prev,
      { date: new Date().toISOString().slice(0, 10), title: "", time: "", end_time: "" },
    ]);
  }

  return (
    <div className="p-4 md:p-6 max-w-5xl mx-auto space-y-5">
      <div>
        <Link href="/" className="text-xs text-gray-500 hover:underline">← Home</Link>
        <h1 className="text-xl md:text-2xl font-bold text-gray-900 mt-1">
          Calendar Image → Events
        </h1>
        <p className="text-xs text-gray-500 mt-0.5">
          Drop a venue&apos;s monthly calendar image (from Instagram, Facebook, or
          their site). Claude Vision will extract the schedule. Review the
          parsed events, then commit to the events calendar.
        </p>
      </div>

      {/* Venue + month */}
      <section className="bg-white border border-gray-200 rounded-lg p-4 grid gap-3 md:grid-cols-3">
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Venue</label>
          <input
            list="venues-list"
            value={venue}
            onChange={(e) => {
              const v = e.target.value;
              setVenue(v);
              const known = KNOWN_VENUES.find(k => k.name === v);
              if (known) setCity(known.city);
            }}
            className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
          />
          <datalist id="venues-list">
            {KNOWN_VENUES.map(v => <option key={v.name} value={v.name} />)}
          </datalist>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">City</label>
          <input
            value={city}
            onChange={(e) => setCity(e.target.value)}
            className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">
            Month hint <span className="text-gray-400 font-normal">(helps Claude get the year right)</span>
          </label>
          <input
            value={hintMonth}
            onChange={(e) => setHintMonth(e.target.value)}
            placeholder="e.g. June 2026"
            className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
          />
        </div>
      </section>

      {/* Drop zone */}
      <section
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          const f = e.dataTransfer.files?.[0];
          if (f && f.type.startsWith("image/")) pickFile(f);
        }}
        onClick={() => inputRef.current?.click()}
        className={`bg-white border-2 border-dashed rounded-lg p-6 cursor-pointer text-center ${
          dragOver ? "border-emerald-400 bg-emerald-50" : "border-gray-300 hover:border-gray-400"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => pickFile(e.target.files?.[0] || null)}
        />
        {preview ? (
          <div className="space-y-2">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={preview} alt="" className="max-h-72 mx-auto rounded shadow-sm" />
            <div className="text-xs text-gray-500">
              {file?.name} · {file ? Math.round(file.size / 1024) : 0} KB
            </div>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); pickFile(null); }}
              className="text-xs text-gray-500 hover:text-red-600 underline"
            >
              Remove
            </button>
          </div>
        ) : (
          <div className="space-y-2">
            <PhotoIcon className="w-10 h-10 text-gray-400 mx-auto" />
            <div className="text-sm text-gray-700 font-medium">
              Drop a calendar image here, or click to browse
            </div>
            <div className="text-[11px] text-gray-400">
              JPEG, PNG, GIF, or WebP up to 6 MB
            </div>
          </div>
        )}
      </section>

      <div className="flex items-center gap-3">
        <button
          onClick={onParse}
          disabled={parsing || !file}
          className="px-4 py-2 text-sm rounded-md text-white disabled:opacity-50 inline-flex items-center gap-1.5"
          style={{ backgroundColor: eventsBrand }}
        >
          <ArrowUpTrayIcon className="w-4 h-4" />
          {parsing ? "Reading image…" : "Read events from image"}
        </button>
        {events.length > 0 && (
          <span className="text-xs text-gray-500">
            {events.length} parsed
          </span>
        )}
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-md p-3 text-sm text-red-700">
          {error}
        </div>
      )}
      {notes && (
        <div className="bg-amber-50 border border-amber-200 rounded-md p-3 text-xs text-amber-800">
          <span className="font-medium">Claude&apos;s notes:</span> {notes}
        </div>
      )}
      {committed && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-md p-3 text-sm text-emerald-800">
          ✓ Inserted {committed.inserted}, skipped {committed.skipped} duplicates.
        </div>
      )}

      {/* Editable grid */}
      {events.length > 0 && (
        <section className="bg-white border border-gray-200 rounded-lg">
          <div className="flex items-center justify-between p-3 border-b border-gray-200">
            <h2 className="text-sm font-semibold text-gray-900">Review &amp; edit</h2>
            <button
              onClick={addBlankEvent}
              className="text-xs px-2 py-1 rounded border border-gray-300 text-gray-700 hover:bg-gray-50 inline-flex items-center gap-1"
            >
              <PlusIcon className="w-3.5 h-3.5" /> Add row
            </button>
          </div>
          <div className="divide-y divide-gray-100">
            <div className="hidden md:grid grid-cols-[140px_100px_100px_1fr_40px] gap-2 px-3 py-2 text-[10px] uppercase tracking-wider text-gray-500">
              <div>Date</div>
              <div>Start</div>
              <div>End</div>
              <div>Act / title</div>
              <div></div>
            </div>
            {events.map((ev, i) => (
              <div key={i} className="grid grid-cols-2 md:grid-cols-[140px_100px_100px_1fr_40px] gap-2 px-3 py-2">
                <input
                  type="date"
                  value={ev.date}
                  onChange={(e) => updateEvent(i, { date: e.target.value })}
                  className="text-xs px-2 py-1 border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-emerald-300"
                />
                <input
                  type="text"
                  value={ev.time || ""}
                  onChange={(e) => updateEvent(i, { time: e.target.value })}
                  placeholder="8:00 PM"
                  className="text-xs px-2 py-1 border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-emerald-300"
                />
                <input
                  type="text"
                  value={ev.end_time || ""}
                  onChange={(e) => updateEvent(i, { end_time: e.target.value })}
                  placeholder="—"
                  className="text-xs px-2 py-1 border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-emerald-300"
                />
                <input
                  type="text"
                  value={ev.title}
                  onChange={(e) => updateEvent(i, { title: e.target.value })}
                  placeholder="Band / act name"
                  className="text-sm px-2 py-1 border border-gray-300 rounded col-span-2 md:col-span-1 focus:outline-none focus:ring-1 focus:ring-emerald-300"
                />
                <button
                  onClick={() => removeEvent(i)}
                  className="text-gray-400 hover:text-red-600 p-1"
                  title="Remove"
                >
                  <TrashIcon className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
          <div className="p-3 border-t border-gray-200 flex items-center justify-between">
            <button
              onClick={() => setEvents([])}
              className="text-xs text-gray-500 hover:text-gray-700"
            >
              <XMarkIcon className="w-3.5 h-3.5 inline" /> Discard all
            </button>
            <button
              onClick={onCommit}
              disabled={committing || events.length === 0}
              className="px-4 py-2 text-sm rounded-md text-white disabled:opacity-50 inline-flex items-center gap-1.5"
              style={{ backgroundColor: eventsBrand }}
            >
              <CheckIcon className="w-4 h-4" />
              {committing ? "Saving…" : `Add ${events.length} to calendar`}
            </button>
          </div>
        </section>
      )}
    </div>
  );
}
