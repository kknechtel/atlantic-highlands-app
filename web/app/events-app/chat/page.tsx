"use client";

// /chat — single global community feed for events.ahnj.info.
// Polling (~10s) instead of WebSocket; borough scale (~4500 residents)
// makes this plenty.
//
// Compose toolbar offers two "tag" buttons:
//   📅 Tag event   → opens a picker of today/upcoming events
//   📍 Tag check-in → opens a picker of active check-ins
// Selected ref shows as a chip above the input and the saved message
// includes ref_type + ref_id so the feed can render an embedded card.

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ChatBubbleLeftRightIcon, PaperAirplaneIcon, XMarkIcon,
  CalendarDaysIcon, MapPinIcon, TrashIcon,
} from "@heroicons/react/24/outline";
import {
  listCommunityMessages, postCommunityMessage, deleteCommunityMessage,
  getCalendarEvents, listActiveCheckins,
  type CommunityMessage, type CommunityRefKind,
} from "@/lib/api";
import { useAuth } from "@/app/contexts/AuthContext";
import LoginNotice from "@/components/events/LoginNotice";

const eventsBrand = "#1d7a6c";

function fmtTime(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const m = Math.floor(diffMs / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function Avatar({ name, src }: { name: string | null; src: string | null }) {
  const letter = (name || "?").trim().charAt(0).toUpperCase();
  return src ? (
    /* eslint-disable-next-line @next/next/no-img-element */
    <img src={src} alt={name || ""} className="w-9 h-9 rounded-full object-cover flex-shrink-0" />
  ) : (
    <div
      className="w-9 h-9 rounded-full flex items-center justify-center text-white text-sm font-semibold flex-shrink-0"
      style={{ backgroundColor: eventsBrand }}
    >
      {letter}
    </div>
  );
}

type PendingRef = { kind: CommunityRefKind; id: string; label: string; sub?: string } | null;

export default function ChatPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const feedRef = useRef<HTMLDivElement>(null);

  const { data: messages } = useQuery({
    queryKey: ["community-messages"],
    queryFn: () => listCommunityMessages({ limit: 100 }),
    refetchInterval: 10_000,
    refetchIntervalInBackground: false,
  });

  // Auto-scroll to bottom on new messages (only if user was already near the bottom).
  const wasNearBottomRef = useRef(true);
  useEffect(() => {
    if (!feedRef.current) return;
    const el = feedRef.current;
    const onScroll = () => {
      wasNearBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
    };
    el.addEventListener("scroll", onScroll);
    return () => el.removeEventListener("scroll", onScroll);
  }, []);
  useEffect(() => {
    if (!feedRef.current) return;
    if (wasNearBottomRef.current) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight;
    }
  }, [messages]);

  // Pickers
  const [pickerKind, setPickerKind] = useState<CommunityRefKind | null>(null);
  const { data: events } = useQuery({
    queryKey: ["chat-events", new Date().getFullYear()],
    queryFn: () => getCalendarEvents(new Date().getFullYear()),
    enabled: pickerKind === "event",
  });
  const { data: checkins } = useQuery({
    queryKey: ["chat-checkins"],
    queryFn: () => listActiveCheckins(100),
    enabled: pickerKind === "checkin",
  });

  const pickerOptions = useMemo(() => {
    if (pickerKind === "event") {
      const today = new Date().toISOString().slice(0, 10);
      return (events || [])
        .filter(e => e.date >= today)
        .sort((a, b) => a.date.localeCompare(b.date))
        .slice(0, 30)
        .map(e => ({
          kind: "event" as const,
          id: e.id,
          label: e.title,
          sub: [
            new Date(e.date + "T12:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" }),
            e.time || "",
            e.venue || "",
          ].filter(Boolean).join(" · "),
        }));
    }
    if (pickerKind === "checkin") {
      return (checkins || []).slice(0, 30).map(c => ({
        kind: "checkin" as const,
        id: c.id,
        label: c.venue_name,
        sub: [c.city || "", c.user_display_name || ""].filter(Boolean).join(" · "),
      }));
    }
    return [];
  }, [pickerKind, events, checkins]);

  // Compose
  const [body, setBody] = useState("");
  const [pendingRef, setPendingRef] = useState<PendingRef>(null);

  const post = useMutation({
    mutationFn: () => postCommunityMessage({
      body: body.trim(),
      ref_type: pendingRef?.kind,
      ref_id: pendingRef?.id,
    }),
    onSuccess: () => {
      setBody("");
      setPendingRef(null);
      qc.invalidateQueries({ queryKey: ["community-messages"] });
    },
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteCommunityMessage(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["community-messages"] }),
  });

  const canSend = body.trim().length > 0 && !post.isPending;
  // Feed is fetched newest-first; reverse for chronological display.
  const orderedFeed = useMemo(() => [...(messages || [])].reverse(), [messages]);

  return (
    <div className="flex flex-col h-[calc(100vh-120px)] md:h-[calc(100vh-80px)]">
      <div className="px-4 py-3 border-b border-gray-200 bg-white">
        <h1 className="text-base font-semibold text-gray-900 flex items-center gap-2">
          <ChatBubbleLeftRightIcon className="w-4 h-4" style={{ color: eventsBrand }} />
          Around Town
        </h1>
        <p className="text-[11px] text-gray-500">
          One feed for the three towns · tag an event or check-in
        </p>
      </div>

      {/* Feed */}
      <div ref={feedRef} className="flex-1 overflow-y-auto p-3 space-y-3 bg-gray-50">
        {orderedFeed.length === 0 ? (
          <div className="text-center text-sm text-gray-400 py-10">
            No messages yet. Be first to say what&apos;s up.
          </div>
        ) : (
          orderedFeed.map(m => {
            const mine = m.user_id === user?.id;
            return (
              <div key={m.id} className="flex items-start gap-2.5 group">
                <Avatar name={m.user_display_name} src={m.user_picture_url} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline gap-2">
                    <span className="text-sm font-semibold text-gray-900 truncate">
                      {m.user_display_name || "Someone"}
                    </span>
                    <span className="text-[10px] text-gray-400">{fmtTime(m.created_at)}</span>
                  </div>
                  <div className="text-sm text-gray-800 whitespace-pre-wrap break-words">{m.body}</div>
                  {m.ref && (
                    <div className="mt-1.5 inline-flex items-center gap-1.5 max-w-full px-2 py-1.5 rounded-md border bg-white"
                      style={{ borderColor: `${eventsBrand}40` }}>
                      {m.ref.kind === "event"
                        ? <CalendarDaysIcon className="w-3.5 h-3.5 flex-shrink-0" style={{ color: eventsBrand }} />
                        : <MapPinIcon className="w-3.5 h-3.5 flex-shrink-0" style={{ color: eventsBrand }} />}
                      <div className="min-w-0">
                        <div className="text-xs font-medium text-gray-900 truncate">{m.ref.title}</div>
                        {m.ref.subtitle && (
                          <div className="text-[10px] text-gray-500 truncate">{m.ref.subtitle}</div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
                {mine && (
                  <button
                    onClick={() => {
                      if (confirm("Delete this message?")) remove.mutate(m.id);
                    }}
                    className="opacity-0 group-hover:opacity-100 p-1 text-gray-400 hover:text-red-600 rounded transition-opacity"
                    title="Delete"
                  >
                    <TrashIcon className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Compose (logged in) OR sign-in notice (anonymous) */}
      {!user ? (
        <div className="border-t border-gray-200 bg-white p-3"
          style={{ paddingBottom: "calc(env(safe-area-inset-bottom) + 0.75rem)" }}>
          <LoginNotice
            title="Sign in to join the conversation"
            detail="You can read the feed without an account. Posting messages and tagging events needs a quick sign-in."
          />
        </div>
      ) : (
      <div className="border-t border-gray-200 bg-white p-2"
        style={{ paddingBottom: "calc(env(safe-area-inset-bottom) + 0.5rem)" }}>
        {pendingRef && (
          <div className="flex items-center gap-1.5 mb-1.5 px-2 py-1 rounded-md border"
            style={{ borderColor: `${eventsBrand}40`, backgroundColor: `${eventsBrand}10` }}>
            {pendingRef.kind === "event"
              ? <CalendarDaysIcon className="w-3.5 h-3.5" style={{ color: eventsBrand }} />
              : <MapPinIcon className="w-3.5 h-3.5" style={{ color: eventsBrand }} />}
            <div className="min-w-0 flex-1">
              <div className="text-xs font-medium text-gray-900 truncate">{pendingRef.label}</div>
              {pendingRef.sub && (
                <div className="text-[10px] text-gray-500 truncate">{pendingRef.sub}</div>
              )}
            </div>
            <button
              onClick={() => setPendingRef(null)}
              className="p-0.5 text-gray-400 hover:text-gray-700 rounded"
            >
              <XMarkIcon className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
        <div className="flex items-end gap-2">
          <div className="flex gap-1">
            <button
              type="button"
              onClick={() => setPickerKind(pickerKind === "event" ? null : "event")}
              className={`p-2 rounded-md hover:bg-gray-100 ${pickerKind === "event" ? "bg-gray-100" : ""}`}
              title="Tag an event"
            >
              <CalendarDaysIcon className="w-4 h-4 text-gray-500" />
            </button>
            <button
              type="button"
              onClick={() => setPickerKind(pickerKind === "checkin" ? null : "checkin")}
              className={`p-2 rounded-md hover:bg-gray-100 ${pickerKind === "checkin" ? "bg-gray-100" : ""}`}
              title="Tag a check-in"
            >
              <MapPinIcon className="w-4 h-4 text-gray-500" />
            </button>
          </div>
          <textarea
            value={body}
            onChange={e => setBody(e.target.value.slice(0, 1000))}
            onKeyDown={e => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                if (canSend) post.mutate();
              }
            }}
            placeholder="What's happening?"
            rows={1}
            className="flex-1 resize-none px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300 focus:border-emerald-400 max-h-32"
          />
          <button
            onClick={() => canSend && post.mutate()}
            disabled={!canSend}
            className="p-2 rounded-md text-white disabled:opacity-40"
            style={{ backgroundColor: eventsBrand }}
            title="Send (Enter)"
          >
            <PaperAirplaneIcon className="w-4 h-4" />
          </button>
        </div>
      </div>
      )}

      {/* Picker overlay */}
      {pickerKind && (
        <div
          className="fixed inset-0 bg-black/40 z-50 flex items-end sm:items-center justify-center p-4"
          onClick={() => setPickerKind(null)}
        >
          <div
            className="bg-white rounded-xl w-full max-w-sm max-h-[60vh] overflow-y-auto p-3 shadow-xl"
            onClick={e => e.stopPropagation()}
          >
            <div className="text-sm font-semibold text-gray-900 mb-2 sticky top-0 bg-white pb-1">
              Tag {pickerKind === "event" ? "an event" : "a check-in"}
            </div>
            {pickerOptions.length === 0 ? (
              <div className="text-xs text-gray-400 py-4 text-center">
                {pickerKind === "event"
                  ? "No upcoming events to tag."
                  : "No active check-ins to tag right now."}
              </div>
            ) : (
              <ul className="space-y-1">
                {pickerOptions.map(opt => (
                  <li key={`${opt.kind}-${opt.id}`}>
                    <button
                      onClick={() => {
                        setPendingRef({ kind: opt.kind, id: opt.id, label: opt.label, sub: opt.sub });
                        setPickerKind(null);
                      }}
                      className="w-full text-left p-2 rounded-md hover:bg-gray-50"
                    >
                      <div className="text-sm text-gray-900 truncate">{opt.label}</div>
                      {opt.sub && (
                        <div className="text-[11px] text-gray-500 truncate">{opt.sub}</div>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
