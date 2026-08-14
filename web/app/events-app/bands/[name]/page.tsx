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
import { venueHref } from "@/lib/eventLinks";
import { youtubeEmbedUrl } from "@/lib/youtube";
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

  // Genre chips come from the enriched profile first (scraped from the
  // band's own pages, with a source URL), falling back to the guide's
  // curated tags. Deduped case-insensitively so "Rock" from both sources
  // renders once.
  const genreTags = useMemo(() => {
    const fromProfile = (profile?.genres || "")
      .split(",").map(s => s.trim()).filter(Boolean);
    const merged = [...fromProfile];
    for (const t of guide?.tags || []) {
      if (!merged.some(m => m.toLowerCase() === t.toLowerCase())) merged.push(t);
    }
    return merged;
  }, [profile?.genres, guide]);

  const hasAbout = genreTags.length > 0 || !!guide?.description || !!guide?.vibe;

  // Prefer a video an admin or the enrichment picked. Otherwise fall back
  // to the known YouTube link, which only embeds when it's a /channel/UC…
  // URL — @handles and /user/ names can't be resolved without the Data
  // API, so those stay as the plain "YouTube ↗" button below.
  const embedUrl = useMemo(() => {
    const known = findKnownBandLinks(bandName);
    return youtubeEmbedUrl(profile?.video_url) || youtubeEmbedUrl(known?.youtube);
  }, [profile?.video_url, bandName]);

  // Admin inline edit
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Omit<BandProfile, "name">>({
    facebook_url: "", instagram_url: "", website_url: "",
    bandsintown_url: "", bio: "", photo_url: "",
    genres: "", genre_source_url: "",
    rating: null, rating_count: null, rating_source_url: "",
    video_url: "",
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
        genres: profile.genres || "",
        genre_source_url: profile.genre_source_url || "",
        rating: profile.rating,
        rating_count: profile.rating_count,
        rating_source_url: profile.rating_source_url || "",
        video_url: profile.video_url || "",
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
      genres: draft.genres?.trim() || null,
      genre_source_url: draft.genre_source_url?.trim() || null,
      // A rating without a source URL is dropped rather than saved — the
      // page won't display one it can't attribute, so storing it would
      // just be an invisible unsourced claim about a real musician.
      rating: draft.rating_source_url?.trim() ? draft.rating : null,
      rating_count: draft.rating_source_url?.trim() ? draft.rating_count : null,
      rating_source_url: draft.rating_source_url?.trim() || null,
      video_url: draft.video_url?.trim() || null,
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

      {/* What kind of act — genre/style overview. Sits above the dates so
          you learn what the band is before scanning where they play. */}
      {hasAbout && (
        <section className="bg-white border border-gray-200 rounded-lg p-4">
          <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
            What kind of act
          </div>

          {genreTags.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-3">
              {genreTags.map(t => (
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

          {guide?.description && (
            <p className="text-sm text-gray-800">{guide.description}</p>
          )}

          {guide?.vibe && (
            <div className="mt-3 pt-3 border-t border-gray-100">
              <div className="text-[11px] uppercase tracking-wider text-gray-400 mb-0.5">
                Vibe
              </div>
              <p className="text-sm text-gray-700">{guide.vibe}</p>
            </div>
          )}

          {/* Only a rating that names its source is shown, and it links
              to the page that published it.

              The band guide's own 1-5 score is deliberately NOT rendered.
              It scores fit for a beach-club wedding booking, not quality:
              of the five guide acts that actually play here, three sit at
              1/5 under "avoid-wrong-style" — Moroccan Sheepherders scores
              1/5 for being a jam band, not for being bad at it. Published
              bare on a borough page it reads as a verdict on a working
              local musician, which is not a claim this app has any basis
              to make. The guide's descriptive fields (tags, vibe,
              description) are shown above; its scores stay out. */}
          {profile?.rating != null && profile.rating_source_url && (
            <div className="mt-3 pt-3 border-t border-gray-100 text-sm text-gray-700">
              <span className="font-medium">{profile.rating}/5</span>
              {profile.rating_count ? ` from ${profile.rating_count} reviews` : ""}
              {" · "}
              <a
                href={profile.rating_source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[11px] underline text-gray-500 hover:text-gray-800"
              >
                source ↗
              </a>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-3 pt-3 border-t border-gray-100 text-[11px] text-gray-500">
            {guide?.weddingBand != null && (
              <span>{guide.weddingBand ? "Books weddings & private events" : "Bar / club act"}</span>
            )}
            {guide?.regularVenues && <span>Regulars at {guide.regularVenues}</span>}
            {profile?.genre_source_url && (
              <a
                href={profile.genre_source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="underline hover:text-gray-800"
              >
                Genre from the band&apos;s own page ↗
              </a>
            )}
          </div>
        </section>
      )}

      {/* Video — only when the URL converts to an embed. A broken iframe
          is worse than the "YouTube ↗" button we already show. */}
      {embedUrl && (
        <section>
          <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
            Watch
          </div>
          <div
            className="relative w-full overflow-hidden rounded-lg border border-gray-200 bg-black"
            style={{ aspectRatio: "16 / 9" }}
          >
            <iframe
              src={embedUrl}
              title={`${bandName} on YouTube`}
              className="absolute inset-0 w-full h-full"
              style={{ border: 0 }}
              loading="lazy"
              referrerPolicy="strict-origin-when-cross-origin"
              allow="accelerometer; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
              allowFullScreen
            />
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
              <div>
                <label className="block text-[10px] uppercase tracking-wider text-gray-500 mb-0.5">
                  YouTube video URL
                </label>
                <input
                  type="url"
                  value={draft.video_url || ""}
                  onChange={e => setDraft(d => ({ ...d, video_url: e.target.value }))}
                  placeholder="https://www.youtube.com/watch?v=…"
                  className="w-full px-2.5 py-1.5 text-xs border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300 focus:border-emerald-400"
                />
                <p className="text-[10px] text-gray-400 mt-0.5">
                  A video, playlist, or /channel/UC… link. @handles can&apos;t be
                  embedded — paste one of their videos instead.
                </p>
              </div>
              <div>
                <label className="block text-[10px] uppercase tracking-wider text-gray-500 mb-0.5">
                  Genres <span className="text-gray-400 normal-case">(comma separated)</span>
                </label>
                <input
                  type="text"
                  value={draft.genres || ""}
                  onChange={e => setDraft(d => ({ ...d, genres: e.target.value }))}
                  placeholder="Classic Rock, Blues"
                  className="w-full px-2.5 py-1.5 text-xs border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300 focus:border-emerald-400"
                />
              </div>
              <div>
                <label className="block text-[10px] uppercase tracking-wider text-gray-500 mb-0.5">
                  Genre source URL
                </label>
                <input
                  type="url"
                  value={draft.genre_source_url || ""}
                  onChange={e => setDraft(d => ({ ...d, genre_source_url: e.target.value }))}
                  placeholder="https://… (the band's own page)"
                  className="w-full px-2.5 py-1.5 text-xs border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300 focus:border-emerald-400"
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-[10px] uppercase tracking-wider text-gray-500 mb-0.5">
                    Rating (0-5)
                  </label>
                  <input
                    type="number" min={0} max={5} step={0.1}
                    value={draft.rating ?? ""}
                    onChange={e => setDraft(d => ({
                      ...d, rating: e.target.value === "" ? null : Number(e.target.value),
                    }))}
                    className="w-full px-2.5 py-1.5 text-xs border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300 focus:border-emerald-400"
                  />
                </div>
                <div>
                  <label className="block text-[10px] uppercase tracking-wider text-gray-500 mb-0.5">
                    Review count
                  </label>
                  <input
                    type="number" min={0} step={1}
                    value={draft.rating_count ?? ""}
                    onChange={e => setDraft(d => ({
                      ...d, rating_count: e.target.value === "" ? null : Number(e.target.value),
                    }))}
                    className="w-full px-2.5 py-1.5 text-xs border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300 focus:border-emerald-400"
                  />
                </div>
              </div>
              <div>
                <label className="block text-[10px] uppercase tracking-wider text-gray-500 mb-0.5">
                  Rating source URL
                </label>
                <input
                  type="url"
                  value={draft.rating_source_url || ""}
                  onChange={e => setDraft(d => ({ ...d, rating_source_url: e.target.value }))}
                  placeholder="https://… (page that publishes the rating)"
                  className="w-full px-2.5 py-1.5 text-xs border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-300 focus:border-emerald-400"
                />
                <p className="text-[10px] text-gray-400 mt-0.5">
                  Ratings without a source are discarded — we only show a score
                  we can point at. Don&apos;t enter your own opinion here.
                </p>
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
                    {venueHref(s) ? (
                      <Link href={venueHref(s)!} className="hover:underline" style={{ color: eventsBrand }}>
                        {s.venue}
                      </Link>
                    ) : (
                      <span>{s.location || "—"}</span>
                    )}
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
