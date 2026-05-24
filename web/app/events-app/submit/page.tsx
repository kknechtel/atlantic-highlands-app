"use client";

// /submit — Two views in one page:
//   1. The submit-an-event form (all logged-in users)
//   2. The admin moderation list (admins only)
//
// When an admin approves a pending submission, it flips into
// calendar_events with event_type='community' so it surfaces on the
// events app immediately. Rejection stores an optional reason.

import { useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeftIcon, CheckIcon, XMarkIcon, TrashIcon,
  ArrowPathIcon,
} from "@heroicons/react/24/outline";
import {
  createEventSubmission, listEventSubmissions,
  approveEventSubmission, rejectEventSubmission, deleteEventSubmission,
  type EventSubmission, type SubmissionStatus,
} from "@/lib/api";
import { useAuth } from "@/app/contexts/AuthContext";

const eventsBrand = "#1d7a6c";

// Same set the check-in page uses. Free text still allowed.
const KNOWN_VENUES: string[] = [
  "The Proving Ground", "The Chubby Pickle", "The Seafarer",
  "The Sandbox at Seastreak", "Off the Hook", "Bahrs Landing",
  "Inlet Cafe", "One Willow", "Mule Barn Tavern",
  "On the Deck", "Gaslight Gastropub", "Carton Brewing",
  "Copper Canyon", "The Wine Bar", "Atlantic House",
  "Smodcastle Cinemas", "First Ave Playhouse",
  "Donovan's Reef", "Drifthouse by David Burke",
  "McLoone's Rum Runner", "Tommy's Tavern + Tap", "Eventide Grille",
];

function fmtDate(s: string): string {
  const d = new Date(s + "T12:00:00");
  return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}

export default function SubmitEventPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const isAdmin = user?.is_admin === true;

  // Form state
  const [title, setTitle] = useState("");
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [time, setTime] = useState("");
  const [venue, setVenue] = useState("");
  const [city, setCity] = useState("");
  const [description, setDescription] = useState("");
  const [ticketUrl, setTicketUrl] = useState("");
  const [submitterNote, setSubmitterNote] = useState("");
  const [ok, setOk] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = useMutation({
    mutationFn: () => createEventSubmission({
      title: title.trim(),
      event_date: date,
      event_time: time.trim() || undefined,
      venue_name: venue.trim(),
      city: city.trim() || undefined,
      description: description.trim() || undefined,
      ticket_url: ticketUrl.trim() || undefined,
      submitter_note: submitterNote.trim() || undefined,
    }),
    onSuccess: () => {
      setOk(true);
      setErr(null);
      setTitle(""); setTime(""); setVenue(""); setCity("");
      setDescription(""); setTicketUrl(""); setSubmitterNote("");
      qc.invalidateQueries({ queryKey: ["event-submissions"] });
      setTimeout(() => setOk(false), 3000);
    },
    onError: (e: unknown) => setErr(e instanceof Error ? e.message : "Submit failed"),
  });

  const canSubmit = title.trim() && date && venue.trim() && !submit.isPending;

  // Moderation queue
  const [filter, setFilter] = useState<SubmissionStatus | "all">("pending");
  const { data: queue } = useQuery({
    queryKey: ["event-submissions", filter, isAdmin],
    queryFn: () => listEventSubmissions(filter === "all" ? undefined : filter),
    enabled: !!user,
  });

  const approve = useMutation({
    mutationFn: (id: string) => approveEventSubmission(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["event-submissions"] }),
  });
  const reject = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) => rejectEventSubmission(id, reason),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["event-submissions"] }),
  });
  const remove = useMutation({
    mutationFn: (id: string) => deleteEventSubmission(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["event-submissions"] }),
  });

  return (
    <div className="p-4 space-y-6">
      <Link href="/" className="inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-900">
        <ArrowLeftIcon className="w-3.5 h-3.5" /> Back
      </Link>

      <header>
        <h1 className="text-xl font-bold text-gray-900">Submit an event</h1>
        <p className="text-xs text-gray-500 mt-0.5">
          Heard about a show that isn&apos;t on the calendar? Submit it and an admin will review.
        </p>
      </header>

      {/* Form */}
      <section className="bg-white border border-gray-200 rounded-lg p-4 space-y-3">
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Title / band name *</label>
          <input
            value={title}
            onChange={e => setTitle(e.target.value.slice(0, 200))}
            placeholder="Carl Gentry, Trivia Night, Memorial Day Fireworks…"
            className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300 focus:border-emerald-400"
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Date *</label>
            <input
              type="date"
              value={date}
              onChange={e => setDate(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300 focus:border-emerald-400"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Time</label>
            <input
              value={time}
              onChange={e => setTime(e.target.value.slice(0, 40))}
              placeholder="e.g. 8:00 PM"
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300 focus:border-emerald-400"
            />
          </div>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Venue *</label>
          <input
            value={venue}
            onChange={e => setVenue(e.target.value.slice(0, 120))}
            list="known-venues"
            placeholder="Pick from list or type any venue"
            className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300 focus:border-emerald-400"
          />
          <datalist id="known-venues">
            {KNOWN_VENUES.map(v => <option key={v} value={v} />)}
          </datalist>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">City</label>
          <select
            value={city}
            onChange={e => setCity(e.target.value)}
            className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300 focus:border-emerald-400 bg-white"
          >
            <option value="">(unspecified)</option>
            <option value="Atlantic Highlands">Atlantic Highlands</option>
            <option value="Highlands">Highlands</option>
            <option value="Sea Bright">Sea Bright</option>
            <option value="Sandy Hook">Sandy Hook</option>
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Description (optional)</label>
          <textarea
            value={description}
            onChange={e => setDescription(e.target.value.slice(0, 2000))}
            rows={2}
            placeholder="Anything to help an admin verify"
            className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300 focus:border-emerald-400"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Ticket / info URL (optional)</label>
          <input
            type="url"
            value={ticketUrl}
            onChange={e => setTicketUrl(e.target.value)}
            placeholder="https://…"
            className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300 focus:border-emerald-400"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Note to admin (optional)</label>
          <input
            value={submitterNote}
            onChange={e => setSubmitterNote(e.target.value.slice(0, 500))}
            placeholder="e.g. 'I work there', 'saw the flyer'"
            className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300 focus:border-emerald-400"
          />
        </div>

        {err && <div className="text-xs text-red-700">{err}</div>}
        {ok && <div className="text-xs text-emerald-700">Submitted ✓ An admin will review shortly.</div>}

        <div className="flex justify-end">
          <button
            onClick={() => submit.mutate()}
            disabled={!canSubmit}
            className="px-3 py-1.5 text-sm rounded-md text-white disabled:opacity-50"
            style={{ backgroundColor: eventsBrand }}
          >
            {submit.isPending ? "Submitting…" : "Submit for review"}
          </button>
        </div>
      </section>

      {/* Queue — your own submissions or (admin) all submissions */}
      <section>
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
            {isAdmin ? "Moderation queue" : "Your submissions"}
          </h2>
          <div className="flex gap-1">
            {(["pending", "approved", "rejected", "all"] as const).map(s => (
              <button
                key={s}
                onClick={() => setFilter(s)}
                className={`px-2 py-1 text-[10px] rounded-md ${
                  filter === s ? "text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                }`}
                style={filter === s ? { backgroundColor: eventsBrand } : {}}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
        {!queue || queue.length === 0 ? (
          <div className="bg-white border border-gray-200 rounded-lg p-6 text-center text-sm text-gray-400">
            No {filter} submissions.
          </div>
        ) : (
          <ul className="space-y-2">
            {queue.map(s => (
              <QueueRow
                key={s.id} s={s} isAdmin={isAdmin}
                onApprove={() => approve.mutate(s.id)}
                onReject={() => {
                  const r = prompt("Optional reason (shown to submitter):") ?? "";
                  reject.mutate({ id: s.id, reason: r });
                }}
                onDelete={() => {
                  if (confirm("Delete this submission?")) remove.mutate(s.id);
                }}
              />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function QueueRow({
  s, isAdmin, onApprove, onReject, onDelete,
}: {
  s: EventSubmission;
  isAdmin: boolean;
  onApprove: () => void;
  onReject: () => void;
  onDelete: () => void;
}) {
  return (
    <li className="bg-white border border-gray-200 rounded-lg p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-gray-500">
            <span className={`px-1.5 py-0.5 rounded ${
              s.status === "pending" ? "bg-amber-100 text-amber-700"
              : s.status === "approved" ? "bg-emerald-100 text-emerald-700"
              : "bg-gray-100 text-gray-500"
            }`}>{s.status}</span>
            {s.submitter_email && <span className="truncate">{s.submitter_email}</span>}
          </div>
          <div className="text-sm font-semibold text-gray-900 mt-0.5 truncate">{s.title}</div>
          <div className="text-[11px] text-gray-600">
            {fmtDate(s.event_date)}
            {s.event_time && <span> · {s.event_time}</span>}
            <span> · {s.venue_name}</span>
            {s.city && <span className="text-gray-400"> · {s.city}</span>}
          </div>
          {s.description && (
            <div className="text-xs text-gray-700 mt-1.5 whitespace-pre-wrap">{s.description}</div>
          )}
          {s.submitter_note && (
            <div className="text-[11px] text-gray-500 mt-1 italic">Note: {s.submitter_note}</div>
          )}
          {s.admin_note && (
            <div className="text-[11px] text-red-700 mt-1">Admin: {s.admin_note}</div>
          )}
          {s.calendar_event_id && (
            <Link
              href={`/calendar/${s.calendar_event_id}`}
              className="inline-flex items-center gap-1 text-[11px] mt-1.5 hover:underline"
              style={{ color: eventsBrand }}
            >
              <ArrowPathIcon className="w-3 h-3" /> View live event
            </Link>
          )}
        </div>
        <div className="flex flex-col items-end gap-1 flex-shrink-0">
          {isAdmin && s.status === "pending" && (
            <>
              <button
                onClick={onApprove}
                className="p-1.5 rounded text-emerald-600 hover:bg-emerald-50"
                title="Approve"
              >
                <CheckIcon className="w-4 h-4" />
              </button>
              <button
                onClick={onReject}
                className="p-1.5 rounded text-gray-400 hover:text-amber-600 hover:bg-amber-50"
                title="Reject"
              >
                <XMarkIcon className="w-4 h-4" />
              </button>
            </>
          )}
          <button
            onClick={onDelete}
            className="p-1.5 rounded text-gray-300 hover:text-red-600 hover:bg-red-50"
            title="Delete"
          >
            <TrashIcon className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </li>
  );
}
