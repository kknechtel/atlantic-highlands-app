// Built-in URL overrides for bands we already know about.
//
// Why this exists: most local bar bands aren't on Bandsintown/Spotify in any
// useful way, and our default "search-link" buttons can land on bot-gated or
// empty result pages. Rather than asking an admin to curate every band, we
// keep a small hardcoded map of canonical links for the regulars on the
// Atlantic Highlands / Sea Bright / Highlands circuit.
//
// Resolution order in the band page is:
//   1. Admin-curated band_profiles row (DB) — highest priority
//   2. This file (known links)
//   3. Default search URL for the channel
//
// Name matching is case-insensitive and tolerates "The X" / "X" /
// "X Band" / "X" variations — same normalization as bandGuide.ts.

export interface KnownBandLinks {
  website?: string;
  youtube?: string;
  spotify?: string;
  bandcamp?: string;
  bandsintown?: string;
  facebook?: string;
  instagram?: string;
}

const KNOWN: Record<string, KnownBandLinks> = {
  "moroccan sheepherders": {
    website: "https://sheepherders.com/",
    facebook: "https://www.facebook.com/profile.php?id=100063774751835",
    bandsintown: "https://www.bandsintown.com/a/1532933-moroccan-sheepherders",
  },
};

function normalize(s: string): string {
  return (s || "")
    .toLowerCase()
    .replace(/[''`""]/g, "'")
    .replace(/&/g, "and")
    .replace(/[^a-z0-9 ]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function variants(name: string): string[] {
  const base = normalize(name);
  const out = new Set<string>([base]);
  out.add(base.replace(/^the /, ""));
  out.add(base.replace(/ (band|trio|duo|quartet)$/i, ""));
  out.add(base.replace(/^the /, "").replace(/ (band|trio|duo|quartet)$/i, ""));
  return Array.from(out).filter(Boolean);
}

export function findKnownBandLinks(bandName: string): KnownBandLinks | null {
  if (!bandName) return null;
  const wanted = variants(bandName);
  for (const key of Object.keys(KNOWN)) {
    const keyVariants = variants(key);
    for (const w of wanted) {
      if (keyVariants.includes(w)) return KNOWN[key];
    }
  }
  return null;
}
