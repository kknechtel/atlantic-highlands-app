"use client";

// /calendar/[id] — full detail page for a single event with one-tap
// check-in. For music events also embeds the band guide enrichment
// (rating, vibe, tags) and links to /bands/[name] for cross-venue
// schedule. Shows live "who's checked in at this venue right now".

import { use, useMemo, useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeftIcon, CalendarDaysIcon, ClockIcon, MapPinIcon,
  MusicalNoteIcon, TicketIcon, UserGroupIcon, XMarkIcon,
  CheckIcon,
} from "@heroicons/react/24/outline";
import { StarIcon as StarSolid } from "@heroicons/react/24/solid";
import { StarIcon } from "@heroicons/react/24/outline";

import {
  getCalendarEvent, listCheckinsAtVenue, createCheckin,
  getEventRsvp, rsvpToEvent, unrsvpFromEvent,
} from "@/lib/api";
import { findBandInGuide, socialMediaUrl, CATEGORY_LABELS } from "@/lib/bandGuide";
import { useAuth } from "@/app/contexts/AuthContext";

const eventsBrand = "#1d7a6c";

function fmtLongDate(iso: string): string {
  const d = new Date(iso + "T12:00:00");
  return d.toLocaleDateString(undefined, {
    weekday: "long", month: "long", day: "numeric", year: "numeric",
  });
}

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

export default function EventDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { user } = useAuth();
  const qc = useQueryClient();

  const { data: ev, isLoading, error } = useQuery({
    queryKey: ["event", id],
    queryFn: () => getCalendarEvent(id),
  });

  const venueName = ev?.venue || ev?.location || null;

  const { data: hereNow } = useQuery({
    queryKey: ["checkins-at", venueName],
    queryFn: () => venueName ? listCheckinsAtVenue(venueName) : Promise.resolve([]),
    enabled: !!venueName,
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  });

  const guide = useMemo(
    () => (ev && ev.event_type === "live_music" ? findBandInGuide(ev.title) : null),
    [ev],
  );
  const social = socialMediaUrl(guide?.socialMedia);

  const myActive = useMemo(
    () => (hereNow || []).find(c => c.user_id === user?.id) || null,
    [hereNow, user?.id],
  );

  // RSVP — future intent ("I'm going")
  const { data: rsvp } = useQuery({
    queryKey: ["event-rsvp", id],
    queryFn: () => getEventRsvp(id),
    refetchInterval: 90_000,
    refetchIntervalInBackground: false,
  });
  const toggleRsvp = useMutation({
    mutationFn: () => rsvp?.is_going ? unrsvpFromEvent(id) : rsvpToEvent(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["event-rsvp", id] }),
  });

  const [showCheckinModal, setShowCheckinModal] = useState(false);
  const [checkinMessage, setCheckinMessage] = useState("");

  const create = useMutation({
    mutationFn: () => createCheckin({
      venue_name: venueName!,
      city: ev?.city || undefined,
      message: checkinMessage.trim() || undefined,
    }),
    onSuccess: () => {
      setShowCheckinModal(false);
      setCheckinMessage("");
      qc.invalidateQueries({ queryKey: ["checkins-at", venueName] });
      qc.invalidateQueries({ queryKey: ["checkins-active"] });
      qc.invalidateQueries({ queryKey: ["checkin-venues"] });
    },
  });

  if (isLoading) {
    return <div className="p-4 text-sm text-gray-400">Loading…</div>;
  }
  if (error || !ev) {
    return (
      <div className="p-4 space-y-3">
        <Link href="/calendar" className="inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-900">
          <ArrowLeftIcon className="w-3.5 h-3.5" /> Back to events
        </Link>
        <div className="bg-white border border-gray-200 rounded-lg p-6 text-center text-sm text-gray-500">
          Event not found.
        </div>
      </div>
    );
  }

  const isMusic = ev.event_type === "live_music";

  return (
    <div className="p-4 space-y-5">
      <Link href="/calendar" className="inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-900">
        <ArrowLeftIcon className="w-3.5 h-3.5" /> Back to events
      </Link>

      {/* Header */}
      <header>
        <div className="flex items-center gap-2 text-xs text-gray-500 uppercase tracking-wider">
          {isMusic ? <MusicalNoteIcon className="w-3.5 h-3.5" /> : <CalendarDaysIcon className="w-3.5 h-3.5" />}
          <span>{isMusic ? "Live music" : "Event"}</span>
          {ev.city && (
            <>
              <span className="text-gray-300">·</span>
              <span>{ev.city}</span>
            </>
          )}
        </div>
        {isMusic ? (
          <Link
            href={`/bands/${encodeURIComponent(ev.title)}`}
            className="block text-2xl font-bold text-gray-900 mt-1 hover:underline"
          >
            {ev.title}
          </Link>
        ) : (
          <h1 className="text-2xl font-bold text-gray-900 mt-1">{ev.title}</h1>
        )}
      </header>

      {/* Quick facts strip */}
      <section className="bg-white border border-gray-200 rounded-lg p-3 space-y-2">
        <div className="flex items-center gap-2 text-sm text-gray-800">
          <CalendarDaysIcon className="w-4 h-4 text-gray-500" />
          <span>{fmtLongDate(ev.date)}</span>
        </div>
        {ev.time && (
          <div className="flex items-center gap-2 text-sm text-gray-800">
            <ClockIcon className="w-4 h-4 text-gray-500" />
            <span>{ev.time}{ev.end_time ? ` – ${ev.end_time}` : ""}</span>
          </div>
        )}
        {venueName && (
          <div className="flex items-center gap-2 text-sm text-gray-800">
            <MapPinIcon className="w-4 h-4 text-gray-500" />
            <span>{venueName}</span>
          </div>
        )}
        {ev.ticket_url && (
          <a
            href={ev.ticket_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-sm hover:underline"
            style={{ color: eventsBrand }}
          >
            <TicketIcon className="w-4 h-4" />
            Tickets / venue page ↗
          </a>
        )}
      </section>

      {ev.description && (
        <section className="bg-white border border-gray-200 rounded-lg p-3">
          <p className="text-sm text-gray-800 whitespace-pre-wrap">{ev.description}</p>
        </section>
      )}

      {/* Band guide enrichment (music events only) */}
      {guide && (
        <section
          className="bg-white border rounded-lg p-3"
          style={{ borderColor: `${eventsBrand}40` }}
        >
          <div className="flex items-center gap-2 mb-1.5">
            <div className="flex items-center gap-0.5">
              {[1, 2, 3, 4, 5].map(n =>
                n <= guide.rating
                  ? <StarSolid key={n} className="w-3.5 h-3.5" style={{ color: "#eab308" }} />
                  : <StarIcon key={n} className="w-3.5 h-3.5 text-gray-300" />
              )}
            </div>
            <span className="text-[11px] text-gray-500">{CATEGORY_LABELS[guide.category]}</span>
          </div>
          <p className="text-sm text-gray-800">{guide.description}</p>
          {guide.tags.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {guide.tags.map(t => (
                <span key={t} className="text-[10px] px-1.5 py-0.5 rounded-full bg-gray-100 text-gray-600">
                  {t}
                </span>
              ))}
            </div>
          )}
          {social && (
            <a
              href={social.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-block mt-2 text-xs hover:underline"
              style={{ color: eventsBrand }}
            >
              {social.label} ↗
            </a>
          )}
        </section>
      )}

      {/* RSVP / Going — future intent. Renders for every event whether or
          not it has a venue. */}
      <section className="bg-white border border-gray-200 rounded-lg p-3">
        <div className="flex items-center justify-between gap-2 mb-2">
          <div className="text-xs uppercase tracking-wider text-gray-500 flex items-center gap-1.5">
            <UserGroupIcon className="w-3 h-3" />
            Going
            {rsvp && rsvp.count > 0 && (
              <span className="text-gray-400">· {rsvp.count}</span>
            )}
          </div>
          <button
            onClick={() => toggleRsvp.mutate()}
            disabled={toggleRsvp.isPending}
            className={`px-3 py-1 text-xs rounded-md inline-flex items-center gap-1 ${
              rsvp?.is_going
                ? "border border-gray-300 text-gray-700 hover:bg-gray-50"
                : "text-white"
            }`}
            style={!rsvp?.is_going ? { backgroundColor: eventsBrand } : {}}
          >
            {rsvp?.is_going
              ? <><CheckIcon className="w-3.5 h-3.5" /> You&apos;re going</>
              : <>I&apos;m going</>}
          </button>
        </div>
        {rsvp && rsvp.sample_users.length > 0 && (
          <div className="flex items-center gap-1.5 flex-wrap">
            {rsvp.sample_users.slice(0, 12).map(u => (
              <div key={u.user_id} className="flex items-center gap-1 text-[11px] text-gray-600">
                <Avatar name={u.display_name} src={u.picture_url} />
                <span className="max-w-[80px] truncate">{u.display_name || "Someone"}</span>
              </div>
            ))}
            {rsvp.count > rsvp.sample_users.length && (
              <span className="text-[11px] text-gray-400">+{rsvp.count - rsvp.sample_users.length} more</span>
            )}
          </div>
        )}
      </section>

      {/* Check-in action */}
      {venueName && (
        <section className="bg-white border border-gray-200 rounded-lg p-3">
          {myActive ? (
            <div className="flex items-center justify-between gap-2">
              <div className="text-sm text-gray-700">
                You&apos;re checked in here.
              </div>
              <span className="text-[11px] text-gray-400">{fmtAgo(myActive.checked_in_at)}</span>
            </div>
          ) : (
            <button
              onClick={() => setShowCheckinModal(true)}
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
      )}

      {/* Source attribution */}
      {ev.source && (
        <p className="text-[10px] text-gray-400">
          Source: {ev.source}
          {ev.source_url && (
            <>
              {" · "}
              <a href={ev.source_url} target="_blank" rel="noopener noreferrer" className="hover:underline">
                view
              </a>
            </>
          )}
        </p>
      )}

      {/* Check-in modal */}
      {showCheckinModal && venueName && (
        <div
          className="fixed inset-0 bg-black/40 z-50 flex items-end sm:items-center justify-center p-4"
          onClick={() => setShowCheckinModal(false)}
        >
          <div
            className="bg-white rounded-xl w-full max-w-sm p-4 shadow-xl"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-1">
              <div className="text-base font-semibold text-gray-900">Check in at {venueName}</div>
              <button onClick={() => setShowCheckinModal(false)} className="p-1 hover:bg-gray-100 rounded">
                <XMarkIcon className="w-4 h-4 text-gray-400" />
              </button>
            </div>
            {ev.city && <div className="text-xs text-gray-500 mb-3">{ev.city}</div>}
            <textarea
              value={checkinMessage}
              onChange={e => setCheckinMessage(e.target.value.slice(0, 200))}
              placeholder="Optional note (where to find you, etc.)"
              rows={2}
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300 focus:border-emerald-400"
            />
            <div className="flex justify-end gap-2 mt-3">
              <button
                onClick={() => setShowCheckinModal(false)}
                className="px-3 py-1.5 text-sm rounded-md text-gray-600 hover:bg-gray-50"
              >
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
    </div>
  );
}
