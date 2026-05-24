// Local band guide — sourced from a curated Jersey Shore band database
// (Edgewater repo, feature/rsvp-event-integration:src/data/bandGuideData.js).
//
// 45 cover/party bands that play the NJ shore circuit. We use this to
// enrich our scraped event listings: when a scraped band name (e.g.
// "Undisputed" at Donovan's) matches a guide entry, the band detail
// page can show genre tags, a short bio, social handle, and the
// curator's quality rating (1-5).
//
// Some Edgewater-specific fields (the booking date/time for the
// original beach-club use case) are dropped. The fields that survive:
//   - name (display + lookup key)
//   - rating (1-5; surfaces as stars on the band page)
//   - description (one-line bio)
//   - vibe (atmosphere/style)
//   - reviews (qualitative quote)
//   - socialMedia (instagram handle like "@foo" or a fb URL — we render
//                   it as a clickable link when it parses as a handle)
//   - regularVenues (text; comma-separated)
//   - weddingBand (boolean | null)
//   - tags (string[] — genres / vibes)
//   - category (added during port: 'top' | 'strong' | 'caution' | 'mellow' | 'avoid')

export type GuideCategoryId =
  | "top-recommendations"
  | "strong-contenders"
  | "approach-with-caution"
  | "too-mellow-acoustic"
  | "avoid-wrong-style";

export interface GuideBand {
  name: string;
  rating: number;
  description: string;
  vibe: string;
  reviews?: string;
  socialMedia?: string;
  regularVenues?: string;
  weddingBand: boolean | null;
  tags: string[];
  category: GuideCategoryId;
}

export const CATEGORY_LABELS: Record<GuideCategoryId, string> = {
  "top-recommendations": "Top Recommendations",
  "strong-contenders": "Strong Contenders",
  "approach-with-caution": "Approach with Caution",
  "too-mellow-acoustic": "Mellow / Acoustic",
  "avoid-wrong-style": "Wrong Style for High-Energy",
};

// Hand-ported from bandGuideData.js. The original had Edgewater-specific
// date/time fields per band; those are dropped here.
export const BAND_GUIDE: GuideBand[] = [
  // ── top-recommendations ──────────────────────────────────────
  {
    name: "The Benjamins", rating: 5, category: "top-recommendations",
    description: "Specializes in high-energy 90s-2000s rock, pop punk, and alternative covers",
    vibe: "2000s RE-LOAD show featuring hard rock, pop punk, and emo anthems",
    reviews: "4.9/5 stars (160+ reviews)",
    socialMedia: "@thebenjaminsnj",
    regularVenues: "Willie McBride's Hoboken, Just Jake's Montclair",
    weddingBand: false,
    tags: ["90s Rock", "2000s", "Pop Punk", "High Energy"],
  },
  {
    name: "Brian Kirk & The Jirks", rating: 5, category: "top-recommendations",
    description: "8-12 piece band with horns bringing club-like energy to all performances",
    vibe: "Vast catalog spanning all decades with emphasis on rock, soul, pop, and funk",
    reviews: "4.9/5 stars (136+ reviews)",
    socialMedia: "@briankirkandthejirks",
    regularVenues: "Stone Pony, Bar A, Donovan's Reef",
    weddingBand: false,
    tags: ["Rock", "Soul", "Funk", "Horns", "High Energy"],
  },
  {
    name: "Audio Riots", rating: 5, category: "top-recommendations",
    description: "6-core member high-energy band covering 7 decades including punk and EDM",
    vibe: "Led by Dan Toth (compared to Freddie Mercury)",
    reviews: "Amazing! - Sea Girt review",
    socialMedia: "@audioriotnj",
    regularVenues: "Northeast circuit",
    weddingBand: false,
    tags: ["Punk", "EDM", "Classic Rock", "High Energy"],
  },
  {
    name: "The Cliffs", rating: 5, category: "top-recommendations",
    description: "8-piece supergroup playing classic rock from Journey to Van Halen",
    vibe: "High energy without wedding band pretense",
    reviews: "Amazing artists & entertainers!",
    socialMedia: "@thecliffsband",
    regularVenues: "Deal Lake Bar + Co., Red Rock",
    weddingBand: false,
    tags: ["Classic Rock", "80s Rock", "High Energy"],
  },
  {
    name: "Smoking Jackets", rating: 5, category: "top-recommendations",
    description: "Named one of the Top Five Cover Bands in New Jersey",
    vibe: "Fun lovin' classic rock and roll party band",
    reviews: "Top 5 NJ Cover Band",
    socialMedia: "@smokin_jackets",
    regularVenues: "Stone Pony to Bar Anticipation",
    weddingBand: false,
    tags: ["Classic Rock", "Party Band"],
  },
  {
    name: "The Ruckus", rating: 5, category: "top-recommendations",
    description: "Rock, pop, dance with four-part harmonies and party attitude",
    vibe: "Amazing set list, fun stage show, talented musicians",
    reviews: "Top 5 NJ Cover Band",
    regularVenues: "Jersey Shore circuit",
    weddingBand: false,
    tags: ["Rock", "Pop", "Dance", "Party Band"],
  },
  // ── strong-contenders ────────────────────────────────────────
  {
    name: "Pat Roddy Band", rating: 4, category: "strong-contenders",
    description: "Jersey Shore soul/rock focusing on Springsteen, Southside Johnny",
    vibe: "Rock band that also does weddings, not a \"wedding band\"",
    regularVenues: "Stone Pony, Bar A",
    weddingBand: false,
    tags: ["Jersey Shore Rock", "Springsteen", "Soul"],
  },
  {
    name: "The Rockets", rating: 4, category: "strong-contenders",
    description: "Philadelphia's 7-piece powerhouse party band (40 years active)",
    vibe: "High-energy covers across all genres",
    reviews: "TV appearances (CBS, VH1)",
    socialMedia: "@rocketsband",
    regularVenues: "Major venues",
    weddingBand: false,
    tags: ["Party Band", "All Genres", "High Energy"],
  },
  {
    name: "No Standards", rating: 4, category: "strong-contenders",
    description: "Punk/rock/ska energy with unique arrangements",
    vibe: "Plays NYC/NJ bars, nightclubs, and casinos",
    regularVenues: "Resorts World, Hard Rock Atlantic City",
    weddingBand: false,
    tags: ["Punk", "Rock", "Ska", "Alternative"],
  },
  {
    name: "Undisputed", rating: 4, category: "strong-contenders",
    description: "Modern rock/hip-hop fusion covering RAGE, 311, Fall Out Boy",
    vibe: "Where Rock and Pop meet Hip-Hop and Funk",
    regularVenues: "Modern venues",
    weddingBand: false,
    tags: ["Modern Rock", "Hip-Hop", "Nu Metal"],
  },
  {
    name: "Scott Elk", rating: 4, category: "strong-contenders",
    description: "Rock, pop, dance covers from 1960s through today",
    vibe: "Quality venues including Teak (Red Bank)",
    reviews: "Performed with Goo Goo Dolls",
    regularVenues: "Teak, festivals",
    weddingBand: false,
    tags: ["Rock", "Pop", "Dance", "Versatile"],
  },
  {
    name: "Daddy Pop", rating: 4, category: "strong-contenders",
    description: "High-energy performances of classic rock to current hits",
    vibe: "Bruce Springsteen to Bruno Mars",
    reviews: "Clients include Jon Bon Jovi and NFL",
    regularVenues: "Jersey Shore nightclubs",
    weddingBand: true,
    tags: ["Classic Rock", "Current Hits", "High Energy"],
  },
  {
    name: "Blue Collar Band Trio", rating: 4, category: "strong-contenders",
    description: "Six decades of choice rock renditions, groovy jams and surprising mashups",
    vibe: "Old school meets new school",
    socialMedia: "@the_blue_collar_band_nj",
    regularVenues: "Pompton Lakes, NJ area",
    weddingBand: false,
    tags: ["Classic Rock", "Mashups", "Party Band"],
  },
  {
    name: "Those Guys", rating: 4, category: "strong-contenders",
    description: "High energy party rock four piece band from Toms River",
    vibe: "Your mom's favorite band - Rock/Funk/Pop/Party",
    regularVenues: "Jersey Shore area",
    weddingBand: false,
    tags: ["Party Rock", "Funk", "Pop", "High Energy"],
  },
  // ── approach-with-caution ────────────────────────────────────
  { name: "The Kicks", rating: 3, category: "approach-with-caution",
    description: "High-energy 6-piece but limited info available",
    vibe: "Potentially good but needs assessment",
    weddingBand: null, tags: ["Unknown"] },
  { name: "Aaron Manzo", rating: 3, category: "approach-with-caution",
    description: "Acoustic rock covers, may lack full-band energy",
    vibe: "Solo/acoustic act", weddingBand: null, tags: ["Acoustic", "Solo"] },
  { name: "Larry Alter", rating: 3, category: "approach-with-caution",
    description: "Local Jersey Shore guitarist/vocalist",
    vibe: "Versatile covers performer",
    weddingBand: null, tags: ["Covers", "Local", "Versatile"] },
  { name: "Chris Morrisy Duo", rating: 3, category: "approach-with-caution",
    description: "Local cover band performer", vibe: "Duo format covers",
    reviews: "Part of Chris Morrisy Band",
    weddingBand: null, tags: ["Covers", "Duo", "Local"] },
  { name: "Alternate Groove Band", rating: 3, category: "approach-with-caution",
    description: "Rock & soul with horns, could work", vibe: "Needs more research",
    weddingBand: null, tags: ["Rock", "Soul", "Horns"] },
  { name: "Bob Gilmartin", rating: 3, category: "approach-with-caution",
    description: "Highly versatile professional", vibe: "Unknown style preference",
    weddingBand: null, tags: ["Versatile"] },
  { name: "Jeff Lakata", rating: 3, category: "approach-with-caution",
    description: "Somerset/Toms River guitarist with 20 years gigging experience",
    vibe: "Classic rock to country and sing-alongs",
    reviews: "Also plays with Drunken Clams",
    regularVenues: "Jersey Shore circuit",
    weddingBand: false, tags: ["Classic Rock", "Country", "Covers"] },
  { name: "Sketchy Medicine", rating: 3, category: "approach-with-caution",
    description: "Classic Rock-n-Roll Band to Soothe Your Musical Needs",
    vibe: "Classic rock covers", regularVenues: "Forked River, NJ area",
    weddingBand: false, tags: ["Classic Rock", "Rock n Roll"] },
  { name: "The Flying Ivories", rating: 3, category: "approach-with-caution",
    description: "Dueling pianos, interactive but different format",
    vibe: "Request-based performance",
    weddingBand: true, tags: ["Dueling Pianos", "Interactive"] },
  { name: "Sean Patrick & The Alibis", rating: 3, category: "approach-with-caution",
    description: "Promising but limited info", vibe: "Unknown",
    weddingBand: null, tags: ["Unknown"] },
  // ── too-mellow-acoustic ──────────────────────────────────────
  { name: "Tom Vincent", rating: 2, category: "too-mellow-acoustic",
    description: "Solo acoustic performer", vibe: "Mellow afternoon vibes",
    weddingBand: false, tags: ["Acoustic", "Solo", "Mellow"] },
  { name: "Gina Teschke", rating: 2, category: "too-mellow-acoustic",
    description: "Versatile singer but may lean pop/jazz",
    vibe: "Restaurant performer",
    weddingBand: false, tags: ["Pop", "Jazz", "Versatile"] },
  { name: "Charlie Brown", rating: 2, category: "too-mellow-acoustic",
    description: "Wide variety including Christian music",
    vibe: "Family-friendly covers",
    weddingBand: false, tags: ["Covers", "Family-Friendly"] },
  { name: "Trane Stevens Solo", rating: 2, category: "too-mellow-acoustic",
    description: "Multi-genre but limited info", vibe: "Solo performer",
    weddingBand: false, tags: ["Solo", "Multi-Genre"] },
  // ── avoid-wrong-style ────────────────────────────────────────
  { name: "Priceless Band", rating: 1, category: "avoid-wrong-style",
    description: "Traditional polished wedding band",
    vibe: "Classic wedding entertainment",
    weddingBand: true, tags: ["Wedding Band", "Traditional"] },
  { name: "Black Tie Groove Band", rating: 1, category: "avoid-wrong-style",
    description: "Sophistication and polish",
    vibe: "Formal event band",
    weddingBand: true, tags: ["Wedding Band", "Formal"] },
  { name: "Suyat Band", rating: 1, category: "avoid-wrong-style",
    description: "Hawaiian/reggae wedding specialty",
    vibe: "Tropical wedding vibes",
    weddingBand: true, tags: ["Hawaiian", "Reggae", "Wedding"] },
  { name: "E Boro Bandits", rating: 1, category: "avoid-wrong-style",
    description: "Country/wedding focus", vibe: "Country covers",
    weddingBand: true, tags: ["Country", "Wedding"] },
  { name: "The Verdict", rating: 2, category: "avoid-wrong-style",
    description: "Caribbean/reggae specialist", vibe: "Island rhythms",
    weddingBand: false, tags: ["Reggae", "Caribbean"] },
  { name: "XOL Azul Band", rating: 1, category: "avoid-wrong-style",
    description: "Latin rock focus", vibe: "Latin rhythms",
    weddingBand: false, tags: ["Latin", "Rock"] },
  { name: "Jeiris Cook", rating: 1, category: "avoid-wrong-style",
    description: "R&B/soul acoustic, too intimate",
    vibe: "Intimate acoustic sets",
    weddingBand: false, tags: ["R&B", "Soul", "Acoustic"] },
  { name: "Pat Guadagno", rating: 1, category: "avoid-wrong-style",
    description: "Folk/Americana troubadour", vibe: "Singer-songwriter",
    weddingBand: false, tags: ["Folk", "Americana", "Acoustic"] },
  { name: "Rick Winow", rating: 1, category: "avoid-wrong-style",
    description: "Acoustic singer-songwriter",
    vibe: "Restaurant background music",
    weddingBand: false, tags: ["Acoustic", "Singer-Songwriter"] },
  { name: "Rob Dye Duo", rating: 1, category: "avoid-wrong-style",
    description: "Original Americana artist", vibe: "Original music focus",
    weddingBand: false, tags: ["Americana", "Original"] },
  // The guide entry calls them "The Sheepherders" but our scrape labels
  // them "Moroccan Sheepherders" (matches the description). The lookup's
  // variant logic should match either via the "moroccan sheepherders"
  // alias added below.
  { name: "Moroccan Sheepherders", rating: 1, category: "avoid-wrong-style",
    description: "Experimental/jam-band style",
    vibe: "Local NJ act, experimental",
    weddingBand: false, tags: ["Experimental", "Jam Band"] },
  { name: "Megan Cannon", rating: 1, category: "avoid-wrong-style",
    description: "Original country-pop songwriter",
    vibe: "Seattle indie artist",
    weddingBand: false, tags: ["Country-Pop", "Original", "Indie"] },
];

// Normalize for lookup: lowercase, drop punctuation, collapse whitespace.
// Also strip common prefixes/suffixes ("The ", " Band", " Trio") so
// "The Cliffs" matches "Cliffs" and "Cranston Dean Band" matches "Cranston Dean".
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
  // Strip leading "the "
  out.add(base.replace(/^the /, ""));
  // Strip trailing " band" / " trio" / " duo"
  out.add(base.replace(/ (band|trio|duo|quartet)$/i, ""));
  // Both at once
  out.add(base.replace(/^the /, "").replace(/ (band|trio|duo|quartet)$/i, ""));
  return Array.from(out).filter(Boolean);
}

/** Find a guide entry for an event title. Case-insensitive, tolerates
 *  "The X" vs "X" and "Foo Band" vs "Foo". Returns null on miss. */
export function findBandInGuide(eventTitle: string): GuideBand | null {
  if (!eventTitle) return null;
  const wanted = variants(eventTitle);
  for (const band of BAND_GUIDE) {
    const guideVariants = variants(band.name);
    for (const w of wanted) {
      if (guideVariants.includes(w)) return band;
    }
  }
  return null;
}

/** Render a socialMedia field as a clickable URL. Returns null if we
 *  can't infer a platform. */
export function socialMediaUrl(handle: string | undefined): { url: string; label: string } | null {
  if (!handle) return null;
  const s = handle.trim();
  if (s.startsWith("http")) return { url: s, label: s.replace(/^https?:\/\//, "") };
  if (s.startsWith("@")) {
    const name = s.slice(1);
    return { url: `https://www.instagram.com/${name}`, label: s };
  }
  if (s.toLowerCase().startsWith("facebook:")) {
    const q = encodeURIComponent(s.replace(/^facebook:\s*/i, ""));
    return { url: `https://www.facebook.com/search/top?q=${q}`, label: "Facebook" };
  }
  return null;
}
