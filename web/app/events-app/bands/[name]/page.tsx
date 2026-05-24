"use client";

// /bands/[name] — every upcoming show for one band/act across all venues.
//
// The user's example: "Moroccan Sheepherders" plays at multiple spots —
// click their name on a calendar row and see every date + venue.
//
// Data: we don't have a `bands` table yet. We filter the cached calendar
// events by exact title (case-insensitive). Good enough at borough scale.
//
// "Find them online" links resolve in three layers:
//   1. Admin-curated band_profiles row (DB) — admin edits inline
//   2. Hardcoded canonical URLs in lib/knownBandLinks.ts
//   3. Default search URLs (YouTube, Spotify, Google, etc.)

import { use, useMemo, useState, useEffect } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getCalendarEvents, getBandProfile, upsertBandProfile,
  type CalendarEvent, type BandProfile,
} from "@/lib/api";
import { findKnownBandLinks } from "@/lib/knownBandLinks";
import { useAuth } from "@/app/contexts/AuthContext";
import {
  ArrowLeftIcon, MusicalNoteIcon,
  MapPinIcon, PencilIcon,
} from "@heroicons/react/24/outline";

const eventsBrand = "#1d7a6c";

function fmtDate(iso: string): string {
  const d = new Date(iso + "T12:00:00");
  return d.toLocaleDateString(undefined, {
    weekday: "short", month: "short", day: "numeric",
  });
}

type LinkOut = { label: string; href: string };

// Default search URLs to use when we have no curated/known URL for a band.
// Notes on what's been pruned vs. what was here before:
//   - Instagram's keyword-search endpoint is gated (requires login, returns
//     404 for guests) so we don't surface it as a default — better to have
//     no link than a broken one.
//   - Bandsintown's `searchSuggestions` URL is an internal AJAX endpoint
//     that renders an empty page when opened directly. Use Google with a
//     site: scope instead — it lands on the artist's real BIT page.
//   - Google search no longer biases toward "NJ Atlantic Highlands": that
//     biased away from the band's actual website/Spotify/YouTube hits.
function defaultLinks(bandName: string): LinkOut[] {
  const q = encodeURIComponent(`${bandName} band`);
  const qExact = encodeURIComponent(`"${bandName}"`);
  return [
    { label: "YouTube",     href: `https://www.youtube.com/results?search_query=${q}` },
    { label: "Spotify",     href: `https://open.spotify.com/search/${encodeURIComponent(bandName)}/artists` },
    { label: "Bandsintown", href: `https://www.google.com/search?q=site%3Abandsintown.com+${qExact}` },
    { label: "Facebook",    href: `https://www.facebook.com/search/top?q=${encodeURIComponent(bandName)}` },
    { label: "Google",      href: `https://www.google.com/search?q=${q}` },
  ];
}

// Merge admin-curated profile URLs and built-in known-band URLs on top of
// the defaults so labels stay in a predictable order but any specific URL
// we *do* know about overrides the corresponding search link.
function mergeLinks(
  bandName: string,
  profile: BandProfile | null | undefined,
): LinkOut[] {
  const known = findKnownBandLinks(bandName);
  const overrides: Partial<Record<string, string>> = {
    Website:     profile?.website_url     || known?.website     || undefined,
    YouTube:     known?.youtube           || undefined,
    Spotify:     known?.spotify           || undefined,
    Bandcamp:    known?.bandcamp          || undefined,
    Bandsintown: profile?.bandsintown_url || known?.bandsintown || undefined,
    Facebook:    profile?.facebook_url    || known?.facebook    || undefined,
    Instagram:   profile?.instagram_url   || known?.instagram   || undefined,
  };
  const defaults = defaultLinks(bandName);
  const out: LinkOut[] = [];
  // Website first when we have one.
  if (overrides.Website) out.push({ label: "Website", href: overrides.Website });
  for (const d of defaults) {
    const override = overrides[d.label];
    out.push({ label: d.label, href: override || d.href });
  }
  // Surface curated channels that aren't in the default set.
  for (const extra of ["Bandcamp", "Instagram"] as const) {
    if (overrides[extra]) out.push({ label: extra, href: overrides[extra]! });
  }
  return out;
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

  const { user } = useAuth();
  const qc = useQueryClient();
  const { data: profile } = useQuery({
    queryKey: ["band-profile", bandName.toLowerCase()],
    queryFn: () => getBandProfile(bandName),
  });

  const links = useMemo(() => mergeLinks(bandName, profile), [bandName, profile]);

  // Admin inline edit
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Omit<BandProfile, "name">>({
    facebook_url: "", instagram_url: "", website_url: "",
    bandsintown_url: "", bio: "", photo_url: "",
  });
  useEffect(() => {
    if (profile) {
      setDraft({
        facebook_url: profile.facebook_url || "",
        instagram_url: profile.instagram_url || "",
        website_url: profile.website_url || "",
        bandsintown_url: profile.bandsintown_url || "",
        bio: profile.bio || "",
        photo_url: profile.photo_url || "",
      });
    }
  }, [profile]);
  const save = useMutation({
    mutationFn: () => upsertBandProfile(bandName, {
      facebook_url: draft.facebook_url?.trim() || null,
      instagram_url: draft.instagram_url?.trim() || null,
      website_url: draft.website_url?.trim() || null,
      bandsintown_url: draft.bandsintown_url?.trim() || null,
      bio: draft.bio?.trim() || null,
      photo_url: draft.photo_url?.trim() || null,
    }),
    onSuccess: () => {
      setEditing(false);
      qc.invalidateQueries({ queryKey: ["band-profile", bandName.toLowerCase()] });
    },
  });

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

      {/* Curated profile section. Renders when an admin has filled in
          real URLs; admin sees an edit button. */}
      {(profile || user?.is_admin) && (
        <section
          className="bg-white border rounded-lg p-4"
          style={{ borderColor: `${eventsBrand}40` }}
        >
          <div className="flex items-center justify-between mb-2">
            <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
              Curated profile
            </div>
            {user?.is_admin && !editing && (
              <button
                onClick={() => setEditing(true)}
                className="inline-flex items-center gap-1 text-xs text-gray-500 hover:text-gray-900"
              >
                <PencilIcon className="w-3.5 h-3.5" /> {profile ? "Edit" : "Add"}
              </button>
            )}
          </div>

          {!editing ? (
            <>
              {profile?.photo_url && (
                /* eslint-disable-next-line @next/next/no-img-element */
                <img src={profile.photo_url} alt="" className="w-full h-40 object-cover rounded-md mb-3" />
              )}
              {profile?.bio && (
                <p className="text-sm text-gray-800 whitespace-pre-wrap mb-2">{profile.bio}</p>
              )}
              {profile && (
                <div className="flex flex-wrap gap-2">
                  {profile.facebook_url && (
                    <a href={profile.facebook_url} target="_blank" rel="noopener noreferrer"
                      className="px-2.5 py-1 text-xs rounded-full border border-gray-300 hover:bg-gray-50"
                      style={{ color: eventsBrand }}>
                      Facebook ↗
                    </a>
                  )}
                  {profile.instagram_url && (
                    <a href={profile.instagram_url} target="_blank" rel="noopener noreferrer"
                      className="px-2.5 py-1 text-xs rounded-full border border-gray-300 hover:bg-gray-50"
                      style={{ color: eventsBrand }}>
                      Instagram ↗
                    </a>
                  )}
                  {profile.website_url && (
                    <a href={profile.website_url} target="_blank" rel="noopener noreferrer"
                      className="px-2.5 py-1 text-xs rounded-full border border-gray-300 hover:bg-gray-50"
                      style={{ color: eventsBrand }}>
                      Website ↗
                    </a>
                  )}
                  {profile.bandsintown_url && (
                    <a href={profile.bandsintown_url} target="_blank" rel="noopener noreferrer"
                      className="px-2.5 py-1 text-xs rounded-full border border-gray-300 hover:bg-gray-50"
                      style={{ color: eventsBrand }}>
                      Bandsintown ↗
                    </a>
                  )}
                </div>
              )}
              {!profile && user?.is_admin && (
                <div className="text-xs text-gray-400 italic">No curated profile yet. Click Add.</div>
              )}
            </>
          ) : (
            <div className="space-y-2">
              {(["facebook_url", "instagram_url", "website_url", "bandsintown_url", "photo_url"] as const).map(field => (
                <div key={field}>
                  <label className="block text-[10px] uppercase tracking-wider text-gray-500 mb-0.5">
                    {field.replace(/_url$/, "").replace(/_/g, " ")}
                  </label>
                  <input
                    type="url"
                    value={draft[field] || ""}
                    onChange={e => setDraft(d => ({ ...d, [field]: e.target.value }))}
                    placeholder="https://…"
                    className="w-full px-2.5 py-1.5 text-xs border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300 focus:border-emerald-400"
                  />
                </div>
              ))}
              <div>
                <label className="block text-[10px] uppercase tracking-wider text-gray-500 mb-0.5">Bio</label>
                <textarea
                  value={draft.bio || ""}
                  onChange={e => setDraft(d => ({ ...d, bio: e.target.value }))}
                  rows={3}
                  className="w-full px-2.5 py-1.5 text-xs border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300 focus:border-emerald-400"
                />
              </div>
              <div className="flex justify-end gap-2 pt-1">
                <button
                  onClick={() => setEditing(false)}
                  className="px-3 py-1.5 text-xs rounded-md text-gray-600 hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  onClick={() => save.mutate()}
                  disabled={save.isPending}
                  className="px-3 py-1.5 text-xs rounded-md text-white disabled:opacity-50"
                  style={{ backgroundColor: eventsBrand }}
                >
                  {save.isPending ? "Saving…" : "Save"}
                </button>
              </div>
            </div>
          )}
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
