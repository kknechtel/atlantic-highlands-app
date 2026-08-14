"use client";

// /my-calendar — the caller's saved events, grouped by status.
//
// Three sections:
//   Going      — firm commitments
//   Tentative  — maybe, decide later
//   Follow up  — saved for later (research / waitlist)
//
// Each row is clickable through to /calendar/[id] where the user can
// change status, share, add to a calendar provider, or check in.

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  CalendarDaysIcon, ClockIcon, MapPinIcon, MusicalNoteIcon,
  CheckCircleIcon, QuestionMarkCircleIcon, BookmarkIcon,
} from "@heroicons/react/24/outline";
import { getMyCalendar, type SavedEvent, type RsvpStatus } from "@/lib/api";
import { bandHref, venueHref, eventHref } from "@/lib/eventLinks";
import { RowLink, InlineLink } from "@/components/events/EventRowLink";
import { useAuth } from "@/app/contexts/AuthContext";
import LoginNotice from "@/components/events/LoginNotice";

const eventsBrand = "#1d7a6c";

const SECTIONS: { status: RsvpStatus; label: string; sub: string; Icon: React.ComponentType<{ className?: string }> }[] = [
  { status: "going",     label: "Going",     sub: "I'll be there",   Icon: CheckCircleIcon },
  { status: "tentative", label: "Tentative", sub: "Maybe",           Icon: QuestionMarkCircleIcon },
  { status: "follow_up", label: "Follow up", sub: "Saved for later", Icon: BookmarkIcon },
];

function fmtDate(iso: string): string {
  const d = new Date(iso + "T12:00:00");
  return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}

function Row({ ev }: { ev: SavedEvent }) {
  const isMusic = ev.event_type === "live_music";
  // Dangling RSVP: the underlying event row was purged. Show greyed so
  // the user can still remove it from /calendar/[id], even with no title.
  const missing = !ev.title;
  return (
    <div
      className={`relative flex items-start gap-3 p-3 rounded-lg border hover:shadow-sm transition ${
        missing ? "bg-gray-50 border-gray-200" : "bg-white border-gray-200"
      }`}
    >
      <RowLink href={eventHref(ev.event_id)} label={ev.title || undefined} />
      <div className="w-12 text-center flex-shrink-0">
        {ev.date ? (
          <>
            <div className="text-[10px] text-gray-400 uppercase">
              {new Date(ev.date + "T12:00:00").toLocaleDateString(undefined, { weekday: "short" })}
            </div>
            <div className="text-lg font-bold text-gray-900">
              {new Date(ev.date + "T12:00:00").getDate()}
            </div>
          </>
        ) : (
          <div className="text-[10px] text-gray-400">—</div>
        )}
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
        {/* A dangling RSVP has no title to link from — leave it plain so
            the row still opens the detail page, where it can be removed. */}
        <InlineLink
          href={bandHref(ev)}
          className="text-sm font-semibold text-gray-900 block truncate"
        >
          {ev.title || <span className="italic text-gray-400">Event no longer listed</span>}
        </InlineLink>
        <div className="text-[11px] text-gray-500 flex items-center gap-1.5 flex-wrap">
          {ev.date && <span>{fmtDate(ev.date)}</span>}
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
              <InlineLink href={venueHref(ev)} style={{ color: eventsBrand }}>
                {ev.venue}
              </InlineLink>
            </>
          )}
          {ev.city && (
            <span className="text-[9px] px-1 py-0.5 rounded bg-gray-100">{ev.city}</span>
          )}
        </div>
      </div>
    </div>
  );
}

export default function MyCalendarPage() {
  const { user } = useAuth();

  const { data, isLoading } = useQuery({
    queryKey: ["my-calendar"],
    queryFn: () => getMyCalendar(),
    enabled: !!user,
  });

  if (!user) {
    return (
      <div className="p-4 space-y-4">
        <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
          <BookmarkIcon className="w-5 h-5" style={{ color: eventsBrand }} />
          My Calendar
        </h1>
        <LoginNotice
          title="Sign in to save events"
          detail="When you mark an event Going, Tentative, or Follow up, it'll show here so you can find it later."
        />
      </div>
    );
  }

  const byStatus = new Map<RsvpStatus, SavedEvent[]>([
    ["going", []], ["tentative", []], ["follow_up", []],
  ]);
  for (const e of data || []) byStatus.get(e.status)?.push(e);

  const isEmpty = !isLoading && (!data || data.length === 0);

  return (
    <div className="p-4 space-y-6">
      <div>
        <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
          <BookmarkIcon className="w-5 h-5" style={{ color: eventsBrand }} />
          My Calendar
        </h1>
        <p className="text-xs text-gray-500 mt-0.5">
          Events you&apos;ve saved. Tap any row to change your status or share.
        </p>
      </div>

      {isLoading ? (
        <div className="text-sm text-gray-400">Loading…</div>
      ) : isEmpty ? (
        <div className="bg-white border border-gray-200 rounded-lg p-8 text-center">
          <BookmarkIcon className="w-10 h-10 mx-auto mb-2 text-gray-300" />
          <p className="text-sm text-gray-500">Nothing saved yet.</p>
          <p className="text-xs text-gray-400 mt-1">
            Browse <Link href="/calendar" className="underline" style={{ color: eventsBrand }}>events</Link>{" "}
            and mark them Going, Tentative, or Follow up.
          </p>
        </div>
      ) : (
        SECTIONS.map(({ status, label, sub, Icon }) => {
          const list = byStatus.get(status) || [];
          if (list.length === 0) return null;
          return (
            <section key={status}>
              <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                <Icon className="w-3.5 h-3.5" />
                {label}
                <span className="text-gray-400 normal-case font-normal">· {sub} · {list.length}</span>
              </h2>
              <div className="space-y-2">
                {list.map(ev => <Row key={ev.rsvp_id} ev={ev} />)}
              </div>
            </section>
          );
        })
      )}
    </div>
  );
}
