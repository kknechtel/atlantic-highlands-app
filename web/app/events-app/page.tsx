"use client";

// Events-app home — upcoming events + recent activity. Activity feed
// (check-ins, chat highlights, photos) is filled in by slices 3 and 4;
// for now this page just teases the bottom-tab destinations.

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { getCalendarEvents, isGovtCalendarEvent, type CalendarEvent } from "@/lib/api";
import {
  CalendarDaysIcon, MusicalNoteIcon, BuildingStorefrontIcon,
  MapPinIcon, ChatBubbleLeftRightIcon, ArrowRightIcon,
  PencilSquareIcon,
} from "@heroicons/react/24/outline";

const eventsBrand = "#1d7a6c";

function fmtDate(iso: string): string {
  const d = new Date(iso + "T12:00:00");
  return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

export default function EventsHome() {
  const today = new Date().toISOString().slice(0, 10);
  const in14 = new Date(Date.now() + 14 * 86400000).toISOString().slice(0, 10);

  const { data: allEvents } = useQuery({
    queryKey: ["events-home", new Date().getFullYear()],
    queryFn: () => getCalendarEvents(new Date().getFullYear()),
  });

  // Around Town never shows govt meetings. Uses isGovtCalendarEvent which
  // checks event_type AND falls back to the keyword classifier for legacy
  // 'general' rows so council/planning/etc don't leak in before the
  // server-side backfill runs.
  const upcoming = (allEvents || [])
    .filter((e: CalendarEvent) => e.date >= today && e.date <= in14)
    .filter((e: CalendarEvent) => !isGovtCalendarEvent(e))
    .sort((a, b) => a.date.localeCompare(b.date))
    .slice(0, 8);

  const upcomingMusic = upcoming.filter((e) => e.event_type === "live_music").slice(0, 4);

  return (
    <div className="p-4 space-y-6">
      <div>
        <h1 className="text-xl font-bold text-gray-900">What&apos;s on</h1>
        <p className="text-xs text-gray-500 mt-0.5">Next two weeks around town</p>
      </div>

      {/* Live music shortcut card */}
      {upcomingMusic.length > 0 && (
        <Link
          href="/calendar"
          className="block rounded-xl p-4 text-white"
          style={{ backgroundColor: eventsBrand }}
        >
          <div className="flex items-center gap-2 mb-1">
            <MusicalNoteIcon className="w-4 h-4" />
            <span className="text-[11px] uppercase tracking-wider opacity-80">Live music</span>
          </div>
          <div className="text-lg font-semibold">
            {upcomingMusic.length} {upcomingMusic.length === 1 ? "show" : "shows"} this week
          </div>
          <div className="text-xs opacity-90 mt-1">
            {upcomingMusic.slice(0, 3).map((m) => m.venue).filter(Boolean).join(" · ")}
          </div>
          <div className="flex items-center gap-1 mt-2 text-xs">
            <span>See all</span>
            <ArrowRightIcon className="w-3.5 h-3.5" />
          </div>
        </Link>
      )}

      {/* Upcoming list */}
      <section>
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
          Coming up
        </h2>
        {upcoming.length === 0 ? (
          <div className="bg-white border border-gray-200 rounded-lg p-6 text-center text-sm text-gray-400">
            Nothing on the calendar in the next two weeks.
          </div>
        ) : (
          <ul className="bg-white border border-gray-200 rounded-lg divide-y divide-gray-100 overflow-hidden">
            {upcoming.map((ev) => (
              <li key={ev.id} className="px-3 py-2.5 flex items-center gap-3">
                <div className="w-10 text-center flex-shrink-0">
                  <div className="text-[9px] uppercase text-gray-400">
                    {new Date(ev.date + "T12:00:00").toLocaleDateString("en-US", { weekday: "short" })}
                  </div>
                  <div className="text-base font-bold text-gray-900 leading-none">
                    {new Date(ev.date + "T12:00:00").getDate()}
                  </div>
                </div>
                <div className="flex-1 min-w-0">
                  <Link
                    href={`/calendar/${ev.id}`}
                    className="text-sm text-gray-900 hover:underline block truncate"
                  >
                    {ev.title}
                  </Link>
                  <div className="text-[11px] text-gray-500 flex items-center gap-1.5">
                    {ev.time && <span>{ev.time}</span>}
                    {ev.venue && (
                      <>
                        <span className="text-gray-300">·</span>
                        <span style={{ color: eventsBrand }}>{ev.venue}</span>
                      </>
                    )}
                    {ev.city && (
                      <span className="text-[9px] px-1 py-0.5 rounded bg-gray-100">{ev.city}</span>
                    )}
                  </div>
                </div>
                <Link
                  href={`/calendar/${ev.id}`}
                  className="text-[10px] px-2 py-1 rounded-md border border-gray-200 text-gray-500 hover:text-gray-900 hover:border-gray-300 flex-shrink-0"
                >
                  Open
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Quick-access tiles for the remaining tabs */}
      <section className="grid grid-cols-2 gap-3">
        <Link
          href="/places"
          className="bg-white border border-gray-200 rounded-lg p-4 hover:border-gray-300"
        >
          <BuildingStorefrontIcon className="w-5 h-5 mb-1.5" style={{ color: eventsBrand }} />
          <div className="text-sm font-semibold text-gray-900">Places</div>
          <div className="text-[11px] text-gray-500 mt-0.5">Local business directory</div>
        </Link>
        <Link
          href="/checkin"
          className="bg-white border border-gray-200 rounded-lg p-4 hover:border-gray-300"
        >
          <MapPinIcon className="w-5 h-5 mb-1.5" style={{ color: eventsBrand }} />
          <div className="text-sm font-semibold text-gray-900">Check in</div>
          <div className="text-[11px] text-gray-500 mt-0.5">Who&apos;s out tonight</div>
        </Link>
        <Link
          href="/chat"
          className="bg-white border border-gray-200 rounded-lg p-4 hover:border-gray-300"
        >
          <ChatBubbleLeftRightIcon className="w-5 h-5 mb-1.5" style={{ color: eventsBrand }} />
          <div className="text-sm font-semibold text-gray-900">Chat</div>
          <div className="text-[11px] text-gray-500 mt-0.5">Around-Town feed</div>
        </Link>
        <Link
          href="/calendar"
          className="bg-white border border-gray-200 rounded-lg p-4 hover:border-gray-300"
        >
          <CalendarDaysIcon className="w-5 h-5 mb-1.5" style={{ color: eventsBrand }} />
          <div className="text-sm font-semibold text-gray-900">All events</div>
          <div className="text-[11px] text-gray-500 mt-0.5">Calendar + Live Music filters</div>
        </Link>
        <Link
          href="/submit"
          className="bg-white border border-gray-200 rounded-lg p-4 hover:border-gray-300 col-span-2"
        >
          <PencilSquareIcon className="w-5 h-5 mb-1.5" style={{ color: eventsBrand }} />
          <div className="text-sm font-semibold text-gray-900">Submit an event</div>
          <div className="text-[11px] text-gray-500 mt-0.5">
            Spotted a show we missed? Tell us and an admin will add it.
          </div>
        </Link>
      </section>
    </div>
  );
}
