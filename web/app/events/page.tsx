"use client";

import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { getCalendarEvents, type CalendarEvent } from "@/lib/api";
import Link from "next/link";
import {
  CalendarDaysIcon,
  MusicalNoteIcon,
  FireIcon,
  SparklesIcon,
  MapPinIcon,
  ClockIcon,
  ArrowDownTrayIcon,
  FilmIcon,
  ShoppingBagIcon,
  HeartIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ListBulletIcon,
  Squares2X2Icon,
  BuildingStorefrontIcon,
} from "@heroicons/react/24/outline";

const brandColor = "#385854";

const EVENT_ICONS: Record<string, any> = {
  "fireworks": FireIcon, "movies": FilmIcon, "music": MusicalNoteIcon,
  "festival": SparklesIcon, "easter": HeartIcon, "halloween": SparklesIcon,
  "parade": SparklesIcon, "tree lighting": SparklesIcon, "garage sale": ShoppingBagIcon,
  "karaoke": MusicalNoteIcon, "food truck": ShoppingBagIcon,
  "playhouse": FilmIcon, "theater": FilmIcon, "old love": FilmIcon, "men are dogs": FilmIcon,
};

const EVENT_COLORS: Record<string, string> = {
  "fireworks": "bg-red-50 border-red-200 text-red-700",
  "movies": "bg-purple-50 border-purple-200 text-purple-700",
  "music": "bg-amber-50 border-amber-200 text-amber-700",
  "festival": "bg-orange-50 border-orange-200 text-orange-700",
  "easter": "bg-pink-50 border-pink-200 text-pink-700",
  "halloween": "bg-orange-50 border-orange-200 text-orange-700",
  "karaoke": "bg-violet-50 border-violet-200 text-violet-700",
  "food truck": "bg-teal-50 border-teal-200 text-teal-700",
  "playhouse": "bg-indigo-50 border-indigo-200 text-indigo-700",
  "tree lighting": "bg-emerald-50 border-emerald-200 text-emerald-700",
};

// Venue links
const VENUE_LINKS: Record<string, { name: string; url: string }> = {
  "gaslight": { name: "Gaslight", url: "https://www.facebook.com/p/Gaslight-Gastropub-100067374374903/" },
  "gateway": { name: "Gateway Bar", url: "https://www.facebook.com/gatewayliquors/" },
  "carton": { name: "Carton Brewing", url: "https://www.cartonbrewing.com" },
  "playhouse": { name: "First Ave Playhouse", url: "https://firstaveplayhouse.com" },
  "smodcastle": { name: "Smodcastle Cinemas", url: "https://www.smodcastlecinemas.com" },
  "ahnj_calendar": { name: "Borough Calendar", url: "https://www.ahnj.com/ahnj/Upcoming%20Events/" },
};

function isGovtEvent(title: string): boolean {
  const govt = ["council", "planning board", "commission", "board of education", "boe", "reorganization", "offices"];
  return govt.some(g => title.toLowerCase().includes(g));
}

function isFunEvent(title: string): boolean {
  const notFun = ["hydrant", "cancelled", "rabies", "offices closed", "flushing"];
  const t = title.toLowerCase();
  return !isGovtEvent(title) && !notFun.some(n => t.includes(n));
}

function getEventIcon(title: string) {
  const t = title.toLowerCase();
  for (const [key, Icon] of Object.entries(EVENT_ICONS)) {
    if (t.includes(key)) return Icon;
  }
  return CalendarDaysIcon;
}

function getEventColor(title: string): string {
  const t = title.toLowerCase();
  for (const [key, style] of Object.entries(EVENT_COLORS)) {
    if (t.includes(key)) return style;
  }
  return "bg-gray-50 border-gray-200 text-gray-700";
}

export default function EventsPage() {
  const [filter, setFilter] = useState<"all" | "fun" | "govt">("fun");
  const [view, setView] = useState<"list" | "calendar">("list");
  const [currentDate, setCurrentDate] = useState(new Date());

  const year = currentDate.getFullYear();
  const month = currentDate.getMonth();
  const monthName = currentDate.toLocaleDateString("en-US", { month: "long", year: "numeric" });

  const { data: events } = useQuery({
    queryKey: ["all-events", year],
    queryFn: () => getCalendarEvents(year),
  });

  // Filter for current month
  const monthEvents = useMemo(() => {
    let list = (events || []).filter(e => {
      const d = new Date(e.date + "T12:00:00");
      return d.getMonth() === month && d.getFullYear() === year;
    });
    if (filter === "fun") list = list.filter(e => isFunEvent(e.title));
    if (filter === "govt") list = list.filter(e => isGovtEvent(e.title));
    return list.sort((a, b) => a.date.localeCompare(b.date));
  }, [events, month, year, filter]);

  // Upcoming highlights (next 30 days)
  const upcoming = useMemo(() => {
    const today = new Date().toISOString().slice(0, 10);
    const in30 = new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 10);
    return (events || [])
      .filter(e => e.date >= today && e.date <= in30 && isFunEvent(e.title))
      .sort((a, b) => a.date.localeCompare(b.date))
      .slice(0, 6);
  }, [events]);

  // Calendar grid data
  const calendarDays = useMemo(() => {
    const firstDay = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const days: (number | null)[] = [];
    for (let i = 0; i < firstDay; i++) days.push(null);
    for (let d = 1; d <= daysInMonth; d++) days.push(d);
    return days;
  }, [year, month]);

  const eventsByDate = useMemo(() => {
    const map = new Map<string, CalendarEvent[]>();
    for (const ev of monthEvents) {
      if (!map.has(ev.date)) map.set(ev.date, []);
      map.get(ev.date)!.push(ev);
    }
    return map;
  }, [monthEvents]);

  const prevMonth = () => setCurrentDate(new Date(year, month - 1, 1));
  const nextMonth = () => setCurrentDate(new Date(year, month + 1, 1));

  const downloadICS = (event: CalendarEvent) => {
    const dateStr = event.date.replace(/-/g, "");
    const ics = [
      "BEGIN:VCALENDAR", "VERSION:2.0", "BEGIN:VEVENT",
      `DTSTART;VALUE=DATE:${dateStr}`,
      `SUMMARY:${event.title}${event.time ? " " + event.time : ""}`,
      `LOCATION:${(event as any).location || "Atlantic Highlands, NJ"}`,
      "END:VEVENT", "END:VCALENDAR",
    ].join("\r\n");
    const blob = new Blob([ics], { type: "text/calendar" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
    a.download = `ah-event-${event.date}.ics`; a.click();
  };

  return (
    <div className="p-4 md:p-8 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Events & Entertainment</h1>
          <p className="text-sm text-gray-500 mt-0.5">What's happening in Atlantic Highlands</p>
        </div>
        <Link href="/local-business" className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-gray-200 rounded-lg hover:bg-gray-50">
          <BuildingStorefrontIcon className="w-3.5 h-3.5" /> Local Businesses
        </Link>
      </div>

      {/* Upcoming highlights */}
      {upcoming.length > 0 && filter !== "govt" && (
        <div className="mb-6">
          <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Coming Up</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
            {upcoming.map((ev, i) => {
              const Icon = getEventIcon(ev.title);
              const style = getEventColor(ev.title);
              const d = new Date(ev.date + "T12:00:00");
              const venue = VENUE_LINKS[ev.source];
              return (
                <div key={i} className={`rounded-xl border p-3 ${style} transition-shadow hover:shadow-md`}>
                  <div className="flex items-start gap-2">
                    <div className="w-10 h-10 rounded-lg flex flex-col items-center justify-center flex-shrink-0 bg-white/60 text-center">
                      <span className="text-[9px] font-bold uppercase">{d.toLocaleDateString("en-US", { month: "short" })}</span>
                      <span className="text-base font-bold leading-none">{d.getDate()}</span>
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1 mb-0.5">
                        <Icon className="w-3.5 h-3.5 flex-shrink-0" />
                        <h3 className="font-semibold text-xs truncate">{ev.title}</h3>
                      </div>
                      {ev.time && <p className="text-[10px] opacity-75">{ev.time}</p>}
                      {venue && (
                        <a href={venue.url} target="_blank" rel="noopener noreferrer" className="text-[10px] underline opacity-75 hover:opacity-100">
                          {venue.name}
                        </a>
                      )}
                    </div>
                    <button onClick={() => downloadICS(ev)} className="p-0.5 opacity-40 hover:opacity-100" title="Add to calendar">
                      <ArrowDownTrayIcon className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Controls */}
      <div className="flex items-center gap-2 mb-4 flex-wrap">
        {([["fun", "Entertainment"], ["govt", "Government"], ["all", "All"]] as const).map(([key, label]) => (
          <button key={key} onClick={() => setFilter(key)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              filter === key ? "text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
            style={filter === key ? { backgroundColor: brandColor } : {}}>
            {label}
          </button>
        ))}
        <div className="flex-1" />
        {/* View toggle */}
        <div className="flex border border-gray-300 rounded-lg overflow-hidden">
          <button onClick={() => setView("list")} className={`p-1.5 ${view === "list" ? "bg-gray-200" : "hover:bg-gray-100"}`} title="List view">
            <ListBulletIcon className="w-4 h-4 text-gray-600" />
          </button>
          <button onClick={() => setView("calendar")} className={`p-1.5 ${view === "calendar" ? "bg-gray-200" : "hover:bg-gray-100"}`} title="Calendar view">
            <Squares2X2Icon className="w-4 h-4 text-gray-600" />
          </button>
        </div>
      </div>

      {/* Month navigation */}
      <div className="flex items-center justify-between mb-4 bg-white rounded-xl shadow-sm border border-gray-200 px-4 py-3">
        <button onClick={prevMonth} className="p-1 hover:bg-gray-100 rounded"><ChevronLeftIcon className="w-5 h-5 text-gray-600" /></button>
        <h2 className="text-lg font-semibold text-gray-900">{monthName}</h2>
        <button onClick={nextMonth} className="p-1 hover:bg-gray-100 rounded"><ChevronRightIcon className="w-5 h-5 text-gray-600" /></button>
      </div>

      {/* Calendar View */}
      {view === "calendar" ? (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
          <div className="grid grid-cols-7 border-b border-gray-200">
            {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map(d => (
              <div key={d} className="text-center text-xs font-medium text-gray-500 py-2 border-r border-gray-100 last:border-0">{d}</div>
            ))}
          </div>
          <div className="grid grid-cols-7">
            {calendarDays.map((day, i) => {
              if (day === null) return <div key={`e-${i}`} className="min-h-[90px] border-r border-b border-gray-100" />;
              const dateStr = `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
              const dayEvents = eventsByDate.get(dateStr) || [];
              const isToday = new Date().toISOString().slice(0, 10) === dateStr;
              return (
                <div key={day} className={`min-h-[90px] p-1 border-r border-b border-gray-100 ${isToday ? "bg-blue-50" : ""}`}>
                  <div className={`text-xs font-medium mb-0.5 ${isToday ? "text-blue-600" : "text-gray-500"}`}>{day}</div>
                  {dayEvents.slice(0, 4).map((ev, ei) => {
                    const venue = VENUE_LINKS[ev.source];
                    return (
                      <div key={ei} className={`text-[8px] leading-tight px-1 py-0.5 rounded mb-0.5 truncate cursor-default ${getEventColor(ev.title)}`}
                        title={`${ev.title}${ev.time ? " " + ev.time : ""}${venue ? " @ " + venue.name : ""}`}>
                        {ev.title}
                      </div>
                    );
                  })}
                  {dayEvents.length > 4 && <div className="text-[8px] text-gray-400">+{dayEvents.length - 4} more</div>}
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        /* List View */
        <div className="space-y-2">
          {monthEvents.length === 0 && (
            <div className="text-center py-12 text-gray-400">
              <CalendarDaysIcon className="w-12 h-12 mx-auto mb-3 text-gray-300" />
              <p>No events found for {monthName}.</p>
            </div>
          )}
          {monthEvents.map((ev, i) => {
            const d = new Date(ev.date + "T12:00:00");
            const Icon = getEventIcon(ev.title);
            const isFun = isFunEvent(ev.title);
            const venue = VENUE_LINKS[ev.source];
            return (
              <div key={i} className={`flex items-center gap-3 p-3 rounded-lg transition-colors ${
                isFun ? "bg-white border border-gray-200 hover:shadow-sm" : "bg-gray-50 hover:bg-gray-100"
              }`}>
                <div className="w-12 text-center flex-shrink-0">
                  <div className="text-[10px] text-gray-400 uppercase">{d.toLocaleDateString("en-US", { weekday: "short" })}</div>
                  <div className="text-lg font-bold text-gray-900">{d.getDate()}</div>
                </div>
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${isFun ? "" : "bg-gray-200"}`}
                  style={isFun ? { backgroundColor: `${brandColor}15`, color: brandColor } : {}}>
                  <Icon className="w-4 h-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className={`text-sm ${isFun ? "font-semibold text-gray-900" : "text-gray-600"}`}>{ev.title}</p>
                  <div className="flex items-center gap-2 text-xs text-gray-400">
                    {ev.time && <span>{ev.time}</span>}
                    {venue && (
                      <a href={venue.url} target="_blank" rel="noopener noreferrer"
                        className="hover:underline" style={{ color: brandColor }}>
                        @ {venue.name}
                      </a>
                    )}
                  </div>
                </div>
                <button onClick={() => downloadICS(ev)} className="p-1.5 text-gray-400 hover:text-gray-600 rounded" title="Download .ics">
                  <ArrowDownTrayIcon className="w-4 h-4" />
                </button>
              </div>
            );
          })}
        </div>
      )}

      {/* Venue links */}
      <div className="mt-8 bg-white rounded-xl shadow-sm border border-gray-200 p-5">
        <h3 className="text-sm font-semibold text-gray-900 mb-3">Venues & Entertainment</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { name: "Gaslight", desc: "Live music Fri nights", url: "https://www.facebook.com/p/Gaslight-Gastropub-100067374374903/", ig: "@gaslight.ah" },
            { name: "Gateway Bar", desc: "Karaoke every Saturday", url: "https://www.facebook.com/gatewayliquors/" },
            { name: "Carton Brewing", desc: "Taproom, food trucks", url: "https://cartonbrewing.com", ig: "@cartonbrewing" },
            { name: "First Ave Playhouse", desc: "Dessert theatre", url: "https://firstaveplayhouse.com" },
            { name: "Smodcastle Cinemas", desc: "Kevin Smith's theater", url: "https://www.smodcastlecinemas.com" },
            { name: "On the Deck", desc: "Waterfront, seasonal music", url: "https://www.facebook.com/OnTheDeckNJ/", ig: "@otdrestaurant" },
            { name: "STRADA", desc: "Wood-fired Italian", url: "https://www.facebook.com/stradapizzabar/", ig: "@stradapizzabar" },
            { name: "SeaStreak Ferry", desc: "Ferry to Manhattan", url: "https://seastreak.com" },
          ].map((v, i) => (
            <a key={i} href={v.url} target="_blank" rel="noopener noreferrer"
              className="p-3 rounded-lg border border-gray-200 hover:border-gray-300 hover:shadow-sm transition-all">
              <p className="text-sm font-medium text-gray-900">{v.name}</p>
              <p className="text-xs text-gray-500">{v.desc}</p>
              {v.ig && <p className="text-[10px] text-pink-500 mt-1">{v.ig}</p>}
            </a>
          ))}
        </div>
      </div>
    </div>
  );
}
