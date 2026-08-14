"use client";

// /bands/[name] — every upcoming show for one band/act across all venues.
//
// The user's example: "Moroccan Sheepherders" plays at multiple spots —
// click their name on a calendar row and see every date + venue.
//
// Data: we don't have a `bands` table yet. We filter the cached calendar
// events by exact title (case-insensitive). Good enough at borough scale.
//
// "Find them online" only shows buttons we have real URLs for, sourced from:
//   1. Admin-curated band_profiles row (DB) — admin edits inline below
//   2. Hardcoded canonical URLs in lib/knownBandLinks.ts
// If we have nothing, a single "Search Google" fallback link replaces the
// row of buttons — search-only links (YouTube/Bandsintown search) made
// people click expecting a band page and land on a results list / login wall.

import { use, useMemo, useState, useEffect } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getCalendarEvents, getBandProfile, upsertBandProfile,
  type CalendarEvent, type BandProfile,
} from "@/lib/api";
import { findKnownBandLinks } from "@/lib/knownBandLinks";
import { findBandInGuide } from "@/lib/bandGuide";
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

// Only emit a button when we have a real URL for it. A "YouTube" or
// "Bandsintown" button that opens a search page is worse than nothing —
// the user clicks expecting the band's page and lands on a results list
// (or, for Instagram/Bandsintown, a login wall or empty AJAX endpoint).
//
// Sources, in priority order:
//   1. Admin-curated band_profiles row (DB)
//   2. lib/knownBandLinks.ts (hardcoded canonical URLs we know)
function resolveLinks(
  bandName: string,
  profile: BandProfile | null | undefined,
): LinkOut[] {
  const known = findKnownBandLinks(bandName);
  const pairs: Array<[string, string | null | undefined]> = [
    ["Website",     profile?.website_url     || known?.website],
    ["YouTube",     known?.youtube],
    ["Spotify",     known?.spotify],
    ["Bandcamp",    known?.bandcamp],
    ["Bandsintown", profile?.bandsintown_url || known?.bandsintown],
    ["Facebook",    profile?.facebook_url    || known?.facebook],
    ["Instagram",   profile?.instagram_url   || known?.instagram],
  ];
  return pairs
    .filter(([, href]) => !!href)
    .map(([label, href]) => ({ label, href: href as string }));
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

  const links = useMemo(() => resolveLinks(bandName, profile), [bandName, profile]);

  // What kind of act this is, from the ported Edgewater guide (42 entries,
  // so most scraped acts miss and the section just doesn't render).
  //
  // We surface only the descriptive fields — genre tags, vibe, one-line
  // description, wedding availability. The guide's `rating`, `reviews` and
  // `category` are deliberately left out: they're one booker's private
  // shortlist notes about named local musicians ("Approach with Caution",
  // "Wrong Style for High-Energy"), which is not something a public borough
  // app should publish about real people. Ratings were already dropped for
  // the same reason in d83c5de.
  const guide = useMemo(() => findBandInGuide(bandName), [bandName]);

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

      {/* What kind of act — genre/style overview from the band guide. */}
      {guide && (
        <section className="bg-white border border-gray-200 rounded-lg p-4">
          <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
            What kind of act
          </div>

          {guide.tags.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-3">
              {guide.tags.map(t => (
                <span
                  key={t}
                  className="px-2.5 py-1 text-xs rounded-full font-medium"
                  style={{ backgroundColor: `${eventsBrand}15`, color: eventsBrand }}
                >
                  {t}
                </span>
              ))}
            </div>
          )}

          {guide.description && (
            <p className="text-sm text-gray-800">{guide.description}</p>
          )}

          {guide.vibe && (
            <div className="mt-3 pt-3 border-t border-gray-100">
              <div className="text-[11px] uppercase tracking-wider text-gray-400 mb-0.5">
                Vibe
              </div>
              <p className="text-sm text-gray-700">{guide.vibe}</p>
            </div>
          )}

          <div className="flex flex-wrap gap-3 mt-3 pt-3 border-t border-gray-100 text-[11px] text-gray-500">
            {guide.weddingBand !== null && (
              <span>{guide.weddingBand ? "Books weddings & private events" : "Bar / club act"}</span>
            )}
            {guide.regularVenues && <span>Regulars at {guide.regularVenues}</span>}
          </div>
        </section>
      )}

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

      {/* Find online — only real URLs (curated profile + knownBandLinks).
          If we have nothing, fall back to a single understated Google link
          rather than a row of buttons that all open useless search pages. */}
      {links.length > 0 ? (
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
      ) : (
        <section className="text-[11px] text-gray-400">
          We don&apos;t have band info yet.{" "}
          <a
            href={`https://www.google.com/search?q=${encodeURIComponent(bandName + " band")}`}
            target="_blank"
            rel="noopener noreferrer"
            className="underline hover:text-gray-600"
          >
            Search Google ↗
          </a>
          {user?.is_admin && (
            <span className="text-gray-400"> · admins: use the Curated profile editor above to add links.</span>
          )}
        </section>
      )}

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
