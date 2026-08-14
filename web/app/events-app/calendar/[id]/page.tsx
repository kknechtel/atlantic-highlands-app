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
  CheckIcon, ArrowDownTrayIcon, ShareIcon, ChatBubbleLeftRightIcon,
  EnvelopeIcon, DevicePhoneMobileIcon, LinkIcon,
} from "@heroicons/react/24/outline";
import { googleCalendarUrl, outlookCalendarUrl, downloadIcs } from "@/lib/calendarLinks";
import { venueHref } from "@/lib/eventLinks";

import {
  getCalendarEvent, listCheckinsAtVenue, createCheckin,
  getEventRsvp, rsvpToEvent, unrsvpFromEvent,
  postCommunityMessage,
  type RsvpStatus,
} from "@/lib/api";
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
  const setStatus = useMutation({
    // Click the active status to remove it; click a different one to switch.
    mutationFn: (target: RsvpStatus) =>
      rsvp?.my_status === target ? unrsvpFromEvent(id) : rsvpToEvent(id, target),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["event-rsvp", id] }),
  });

  const [showCheckinModal, setShowCheckinModal] = useState(false);
  const [checkinMessage, setCheckinMessage] = useState("");
  const [showShareModal, setShowShareModal] = useState(false);
  const [shareMessage, setShareMessage] = useState("");
  const [linkCopied, setLinkCopied] = useState(false);

  const shareToChat = useMutation({
    mutationFn: () => postCommunityMessage({
      body: shareMessage.trim() || `Going to ${ev?.title || "this event"}!`,
      ref_type: "event",
      ref_id: id,
    }),
    onSuccess: () => {
      setShowShareModal(false);
      setShareMessage("");
      qc.invalidateQueries({ queryKey: ["community-messages"] });
    },
  });

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

  // Public URL used by Share buttons. SSR-safe (window only on client).
  const eventUrl = typeof window !== "undefined"
    ? `${window.location.origin}/calendar/${id}`
    : `https://events.ahnj.info/calendar/${id}`;
  const shareSubject = `${ev.title} — ${fmtLongDate(ev.date)}${venueName ? ` @ ${venueName}` : ""}`;
  const shareBody = `${ev.title}\n${fmtLongDate(ev.date)}${ev.time ? ` · ${ev.time}` : ""}${venueName ? `\n${venueName}` : ""}\n\n${eventUrl}`;
  const mailtoUrl = `mailto:?subject=${encodeURIComponent(shareSubject)}&body=${encodeURIComponent(shareBody)}`;
  const smsUrl = `sms:?&body=${encodeURIComponent(shareBody)}`;

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(eventUrl);
      setLinkCopied(true);
      setTimeout(() => setLinkCopied(false), 1500);
    } catch {
      // older browsers — fall back to prompt
      window.prompt("Copy this link:", eventUrl);
    }
  };

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
            {venueHref(ev) ? (
              <Link href={venueHref(ev)!} className="hover:underline" style={{ color: eventsBrand }}>
                {venueName}
              </Link>
            ) : (
              <span>{venueName}</span>
            )}
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

      {/* Add to calendar — Google, Outlook, Apple/ICS */}
      <section className="bg-white border border-gray-200 rounded-lg p-3">
        <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
          Add to your calendar
        </div>
        <div className="flex flex-wrap gap-2">
          <a
            href={googleCalendarUrl({
              title: ev.title, date: ev.date, time: ev.time, end_time: ev.end_time,
              venue: ev.venue, city: ev.city, description: ev.description, ticket_url: ev.ticket_url,
            })}
            target="_blank"
            rel="noopener noreferrer"
            className="px-3 py-1.5 text-xs rounded-md border border-gray-300 text-gray-700 hover:bg-gray-50 inline-flex items-center gap-1.5"
          >
            <CalendarDaysIcon className="w-3.5 h-3.5" /> Google ↗
          </a>
          <a
            href={outlookCalendarUrl({
              title: ev.title, date: ev.date, time: ev.time, end_time: ev.end_time,
              venue: ev.venue, city: ev.city, description: ev.description, ticket_url: ev.ticket_url,
            })}
            target="_blank"
            rel="noopener noreferrer"
            className="px-3 py-1.5 text-xs rounded-md border border-gray-300 text-gray-700 hover:bg-gray-50 inline-flex items-center gap-1.5"
          >
            <CalendarDaysIcon className="w-3.5 h-3.5" /> Outlook ↗
          </a>
          <button
            onClick={() => downloadIcs({
              title: ev.title, date: ev.date, time: ev.time, end_time: ev.end_time,
              venue: ev.venue, city: ev.city, description: ev.description, ticket_url: ev.ticket_url,
            })}
            className="px-3 py-1.5 text-xs rounded-md border border-gray-300 text-gray-700 hover:bg-gray-50 inline-flex items-center gap-1.5"
            title="Apple Calendar / Fantastical / Outlook desktop"
          >
            <ArrowDownTrayIcon className="w-3.5 h-3.5" /> .ics
          </button>
        </div>
      </section>

      {/* Share — to community chat, email, SMS, or copy link */}
      <section className="bg-white border border-gray-200 rounded-lg p-3">
        <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 flex items-center gap-1.5">
          <ShareIcon className="w-3.5 h-3.5" /> Share this event
        </div>
        <div className="flex flex-wrap gap-2">
          {user && (
            <button
              onClick={() => {
                setShareMessage(`Going to ${ev.title}!`);
                setShowShareModal(true);
              }}
              className="px-3 py-1.5 text-xs rounded-md text-white inline-flex items-center gap-1.5"
              style={{ backgroundColor: eventsBrand }}
            >
              <ChatBubbleLeftRightIcon className="w-3.5 h-3.5" /> Post to chat
            </button>
          )}
          <a
            href={mailtoUrl}
            className="px-3 py-1.5 text-xs rounded-md border border-gray-300 text-gray-700 hover:bg-gray-50 inline-flex items-center gap-1.5"
          >
            <EnvelopeIcon className="w-3.5 h-3.5" /> Email
          </a>
          <a
            href={smsUrl}
            className="px-3 py-1.5 text-xs rounded-md border border-gray-300 text-gray-700 hover:bg-gray-50 inline-flex items-center gap-1.5"
          >
            <DevicePhoneMobileIcon className="w-3.5 h-3.5" /> Text
          </a>
          <button
            onClick={copyLink}
            className="px-3 py-1.5 text-xs rounded-md border border-gray-300 text-gray-700 hover:bg-gray-50 inline-flex items-center gap-1.5"
          >
            {linkCopied
              ? <><CheckIcon className="w-3.5 h-3.5 text-green-600" /> Copied</>
              : <><LinkIcon className="w-3.5 h-3.5" /> Copy link</>}
          </button>
        </div>
        {!user && (
          <div className="text-[11px] text-gray-400 mt-2">
            <Link href="/login" className="hover:underline" style={{ color: eventsBrand }}>
              Sign in
            </Link>{" "}
            to share to the community chat.
          </div>
        )}
      </section>

      {/* Save / RSVP — future intent. 3-button selector so users can mark
          a show Going / Tentative / Follow-up. Saved events appear on
          /my-calendar. Re-clicking the active status removes it. */}
      <section className="bg-white border border-gray-200 rounded-lg p-3">
        <div className="flex items-center justify-between gap-2 mb-2">
          <div className="text-xs uppercase tracking-wider text-gray-500 flex items-center gap-1.5">
            <UserGroupIcon className="w-3 h-3" />
            Save to my calendar
            {rsvp && rsvp.going_count > 0 && (
              <span className="text-gray-400">· {rsvp.going_count} going</span>
            )}
          </div>
        </div>
        {!user ? (
          <div className="text-[11px] text-gray-500">
            <Link href="/login" className="hover:underline font-medium" style={{ color: eventsBrand }}>
              Sign in
            </Link>{" "}
            to save this event.
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-2">
            {(["going", "tentative", "follow_up"] as RsvpStatus[]).map(s => {
              const active = rsvp?.my_status === s;
              const label = s === "going" ? "Going" : s === "tentative" ? "Tentative" : "Follow up";
              const sub = s === "going" ? "I'll be there" : s === "tentative" ? "Maybe" : "Save for later";
              return (
                <button
                  key={s}
                  onClick={() => setStatus.mutate(s)}
                  disabled={setStatus.isPending}
                  className={`px-2 py-2 rounded-md text-xs flex flex-col items-center gap-0.5 transition ${
                    active
                      ? "text-white"
                      : "border border-gray-300 text-gray-700 hover:bg-gray-50"
                  }`}
                  style={active ? { backgroundColor: eventsBrand } : {}}
                >
                  <span className="font-medium inline-flex items-center gap-1">
                    {active && <CheckIcon className="w-3.5 h-3.5" />}
                    {label}
                  </span>
                  <span className={`text-[10px] ${active ? "opacity-90" : "text-gray-400"}`}>
                    {sub}
                  </span>
                </button>
              );
            })}
          </div>
        )}
        {rsvp && rsvp.sample_users.length > 0 && (
          <div className="flex items-center gap-1.5 flex-wrap mt-3 pt-3 border-t border-gray-100">
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

      {/* Share-to-chat modal — composes a community message with the event
          attached as a ref so other users see a rich preview card. */}
      {showShareModal && (
        <div
          className="fixed inset-0 bg-black/40 z-50 flex items-end sm:items-center justify-center p-4"
          onClick={() => setShowShareModal(false)}
        >
          <div
            className="bg-white rounded-xl w-full max-w-sm p-4 shadow-xl"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-1">
              <div className="text-base font-semibold text-gray-900">Post to community chat</div>
              <button onClick={() => setShowShareModal(false)} className="p-1 hover:bg-gray-100 rounded">
                <XMarkIcon className="w-4 h-4 text-gray-400" />
              </button>
            </div>
            <div className="text-xs text-gray-500 mb-3">
              Your message links back to <span className="text-gray-700">{ev.title}</span>.
            </div>
            <textarea
              value={shareMessage}
              onChange={e => setShareMessage(e.target.value.slice(0, 280))}
              placeholder="Say something about this event…"
              rows={3}
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300 focus:border-emerald-400"
            />
            <div className="text-[10px] text-gray-400 mt-1 text-right">
              {shareMessage.length}/280
            </div>
            <div className="flex justify-end gap-2 mt-3">
              <button
                onClick={() => setShowShareModal(false)}
                className="px-3 py-1.5 text-sm rounded-md text-gray-600 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={() => shareToChat.mutate()}
                disabled={shareToChat.isPending}
                className="px-3 py-1.5 text-sm rounded-md text-white disabled:opacity-50"
                style={{ backgroundColor: eventsBrand }}
              >
                {shareToChat.isPending ? "Posting…" : "Post"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
