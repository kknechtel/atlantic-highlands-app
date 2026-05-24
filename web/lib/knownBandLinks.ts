// Built-in URL overrides for bands we already know about.
//
// Why this exists: most local bar bands aren't on Bandsintown/Spotify in any
// useful way, and a button that opens a search-results page rather than the
// band's actual page is frustrating. Rather than ask an admin to curate every
// band, we keep a hardcoded map of canonical links for the regulars on the
// Atlantic Highlands / Sea Bright / Highlands circuit.
//
// Resolution order in the band page is:
//   1. Admin-curated band_profiles row (DB) — highest priority
//   2. This file (known links)
//   3. (no fallback — page shows a single understated "Search Google" line)
//
// Name matching is case-insensitive and tolerates "The X" / "X" /
// "X Band" / "X Trio" / "X Duo" / "X Solo" variations. Entries can also
// declare explicit `aliases` for canonical-name variants the auto-stripper
// won't catch (e.g. "Audio Riot" vs "Audio Riots", or full rename like
// "The Highland's Express" vs "JO & the Highland Express").
//
// Verification: every URL in this file was confirmed via web search to
// match a Jersey Shore / Monmouth County NJ act with venue or DJ-handle
// context. Homonyms (e.g. national bands with the same name) were rejected.

export interface KnownBandLinks {
  website?: string;
  youtube?: string;
  spotify?: string;
  bandcamp?: string;
  bandsintown?: string;
  facebook?: string;
  instagram?: string;
  /** Extra lookup names (case-insensitive) that should resolve to this entry. */
  aliases?: string[];
}

// Keys are lowercased "canonical" names. Aliases handle variants the
// normalize+variants function below can't infer (singular/plural,
// total renames, apostrophe edge-cases).
const KNOWN: Record<string, KnownBandLinks> = {
  "10 string": {
    website: "https://www.10stringsacoustic.com/",
    facebook: "https://www.facebook.com/10stringband/",
    instagram: "https://www.instagram.com/10stringband/",
  },
  "80's revolution": {
    website: "https://www.80srevolution-nj.com/",
    facebook: "https://www.facebook.com/80sRevolutionNJ/",
    youtube: "https://www.youtube.com/channel/UCl-1jGRIoc5Qi_Mbtb7M08A",
  },
  "aaron manzo": {
    website: "https://aaronmacoustic.com/bio",
  },
  "aiden villa": {
    website: "https://aidenvilla.com/",
    facebook: "https://www.facebook.com/aidenvillamusic/",
    instagram: "https://www.instagram.com/aidenvillamusic/",
  },
  "amanda & nick": {
    facebook: "https://www.facebook.com/p/Amanda-Nick-Duo-100081686787738/",
    aliases: ["amanda & nick duo", "amanda and nick"],
  },
  "audio riot": {
    // Calendar typically lists them plural; canonical spelling is singular.
    website: "https://www.audioriot.net/",
    facebook: "https://www.facebook.com/audioriotnj/",
    instagram: "https://www.instagram.com/audioriotnj/",
    youtube: "https://www.youtube.com/@audioriot",
    aliases: ["audio riots"],
  },
  "badfish": {
    website: "https://www.badfish.com/",
  },
  "bayshore sandpipers": {
    website: "https://sites.google.com/site/meloreband/",
    instagram: "https://www.instagram.com/bayshoresandpipersband/",
    facebook: "https://www.facebook.com/groups/BayshoreSandpipers/",
  },
  "big hix": {
    website: "https://bighix.com/",
    facebook: "https://www.facebook.com/BIGHIXBAND/",
    bandsintown: "https://www.bandsintown.com/a/7150784-big-hix",
  },
  "blue collar band": {
    website: "https://www.thebluecollarband.net/",
    facebook: "https://www.facebook.com/thebluecollarbandnj/",
    instagram: "https://www.instagram.com/the_blue_collar_band_nj/",
    aliases: ["blue collar band trio"],
  },
  "brendan brophy": {
    // Frontman of NJ cover band "enjoy!"
    website: "https://www.enjoytheband.com/",
  },
  "brian kirk & the jirks": {
    website: "https://www.briankirkandthejirks.com/",
    facebook: "https://www.facebook.com/BrianKirkandtheJirks/",
    aliases: ["brian kirk and the jirks"],
  },
  "bridget larson band": {
    website: "https://www.bridgetlarson.com/",
    facebook: "https://www.facebook.com/thebridgetlarsonband/",
  },
  "carl gentry": {
    website: "https://carlgentrymusic.com/",
    facebook: "https://www.facebook.com/carlgentryband/",
  },
  "carnival dogs": {
    facebook: "https://www.facebook.com/carnivaldogsnj/",
    instagram: "https://www.instagram.com/carnivaldogsnj/",
  },
  "cranston dean": {
    website: "https://www.cranstondean.com/",
    youtube: "https://www.youtube.com/user/CranstonDean",
  },
  "dakota diehl": {
    website: "https://www.dakotadmusic.com/about",
  },
  "dale toth": {
    facebook: "https://www.facebook.com/tothmusic/",
    website: "https://www.tothmusic.com/",
  },
  "dan haase": {
    // Calendar misspells as "Dan Hasse"; canonical is Haase.
    website: "https://danhaase.com/bio",
    aliases: ["dan hasse"],
  },
  "the danjos": {
    website: "https://thedanjos.com/",
    facebook: "https://www.facebook.com/thedanjos/",
    // Calendar variants: Dan Jos / Dan Jo's / Danjos.
    aliases: ["danjos", "dan jos", "dan jo's"],
  },
  "dave matthews tribute band": {
    website: "https://thedmtb.com/",
    facebook: "https://www.facebook.com/thedmtb/",
    aliases: ["the dmtb"],
  },
  "dave mccarthy": {
    website: "https://davemccarthymusic.com/",
    facebook: "https://www.facebook.com/davemccarthymusic/",
  },
  "dead bank": {
    facebook: "https://www.facebook.com/DeadBank/",
    instagram: "https://www.instagram.com/deadbank/",
    bandsintown: "https://www.bandsintown.com/a/1532932-dead-bank",
  },
  "del boca vista": {
    facebook: "https://www.facebook.com/DelBocaVistaBand/",
  },
  "des & the swagmatics": {
    website: "https://www.desandtheswagmatics.com/the-band",
    facebook: "https://www.facebook.com/DesAndTheSwagmatics/",
    aliases: ["des and the swagmatics"],
  },
  "e boro bandits": {
    facebook: "https://www.facebook.com/p/E-Boro-Bandits-100036159622720/",
    instagram: "https://www.instagram.com/eborobandits/",
  },
  "eric and the shipwrecks": {
    website: "https://www.shipwrecksnj.com/",
    instagram: "https://www.instagram.com/shipwrecksnj/",
    youtube: "https://www.youtube.com/user/ShipwrecksNJ",
    aliases: ["eric and the shipwreck", "captain eric and the shipwrecks"],
  },
  "erik mason band": {
    website: "https://erikmasonmusic.com/home",
    facebook: "https://www.facebook.com/erikmasonmusic/",
    instagram: "https://www.instagram.com/erikmasonmusic/",
    aliases: ["erik mason"],
  },
  "fleetwood macked": {
    website: "https://fleetwoodmacked.com/",
    bandsintown: "https://www.bandsintown.com/a/1063750-fleetwood-macked",
  },
  "friend zone": {
    website: "https://www.friendzoneband.com/",
    facebook: "https://www.facebook.com/friendzonebandnj/",
    instagram: "https://www.instagram.com/friendzonebandnj/",
    youtube: "https://www.youtube.com/c/FriendZoneBand",
  },
  "gab cinque band": {
    website: "https://www.thegabcinqueband.com/",
    facebook: "https://www.facebook.com/TheGabCinqueBand/",
    instagram: "https://www.instagram.com/thegabcinqueband/",
  },
  "garden state groove": {
    website: "https://www.gardenstategrooveband.com/",
    facebook: "https://www.facebook.com/gardenstategroove/",
  },
  "grand theft audio": {
    facebook: "https://www.facebook.com/grandtheftaudionj/",
    instagram: "https://www.instagram.com/grandtheftaudio_nj/",
  },
  "guns 4 hire": {
    website: "https://guns4hiretrio.com/",
    facebook: "https://www.facebook.com/guns4hiretrio/",
    instagram: "https://www.instagram.com/guns4hiretrio/",
  },
  "hang loose": {
    facebook: "https://www.facebook.com/hangloosetrio",
  },
  "hard to pet band": {
    instagram: "https://www.instagram.com/hardtopetband/",
  },
  "high strung": {
    website: "https://www.highstrungbandnj.com/",
    facebook: "https://www.facebook.com/highstrungbandnj/",
  },
  "jack mangan": {
    // Calendar spells as "Jack Managan"; canonical IG handle is jackbaileymangan.
    instagram: "https://www.instagram.com/jackbaileymangan/",
    aliases: ["jack managan"],
  },
  "jake and dan": {
    website: "https://jakeanddan.com/",
    facebook: "https://www.facebook.com/jakeanddan",
    aliases: ["jake & dan"],
  },
  "james dalton": {
    facebook: "https://www.facebook.com/jamesdaltonjr/",
  },
  "jess & the drop outs": {
    instagram: "https://www.instagram.com/jess_and_thedropouts/",
    aliases: ["jess and the drop outs", "jess and the dropouts"],
  },
  "jillian rhys mccoy": {
    facebook: "https://www.facebook.com/jillian.r.mccoy/",
    instagram: "https://www.instagram.com/jillianrhysmccoy/",
    spotify: "https://open.spotify.com/artist/1sMoPJNr1WOcY9lwBe2FIN",
  },
  "joe rapolla": {
    website: "https://www.joerapolla.com/",
    aliases: ["joe rappola"],
  },
  "the joe grisanzio band": {
    website: "https://www.joegrisanzio.com/",
    facebook: "https://www.facebook.com/p/Joe-Grisanzio-100093543723667/",
    instagram: "https://www.instagram.com/joegrisanzio/",
    youtube: "https://www.youtube.com/@joegrisanzio",
    aliases: ["joe grisanzio"],
  },
  "john rafferty": {
    website: "https://www.jraffmusic.com/",
  },
  "karly c & the rebel y'all": {
    website: "https://www.rebelyallband.com/",
    facebook: "https://www.facebook.com/RebelYallBand/",
    aliases: ["karly c and the rebel y'all", "rebel y'all"],
  },
  "ken dubman": {
    website: "https://www.kennydubman.com/",
    facebook: "https://www.facebook.com/kennydubman/",
    aliases: ["kenny dubman"],
  },
  "kenny raye band": {
    website: "https://www.kennyrayeband.com/",
  },
  "last call band": {
    website: "https://lastcallbandnj.com/",
    facebook: "https://www.facebook.com/lastcallbandnj/",
  },
  "megan cannon": {
    website: "https://www.megcannon.com/",
    aliases: ["meg cannon"],
  },
  "meg whalen": {
    website: "https://megwhalen.com/",
    facebook: "https://www.facebook.com/megwhalenartist/",
    instagram: "https://www.instagram.com/megwhalen/",
  },
  "moroccan sheepherders": {
    website: "https://sheepherders.com/",
    youtube: "https://www.youtube.com/channel/UCrewkC2zqgQqEKc-mvnW7fw",
    instagram: "https://www.instagram.com/mshmusic/",
    facebook: "https://www.facebook.com/profile.php?id=100063774751835",
    bandsintown: "https://www.bandsintown.com/a/1532933-moroccan-sheepherders",
  },
  "mushmouth": {
    website: "https://www.mushmouth.net/",
    facebook: "https://www.facebook.com/njmushmouth/",
    youtube: "https://www.youtube.com/@mushmouthband",
  },
  "n&d electric duo": {
    website: "https://www.nanddelectricduo.com/",
    facebook: "https://www.facebook.com/NandDElectricDuo/",
    aliases: ["n and d electric duo", "nd electric duo"],
  },
  "newborn kings": {
    website: "https://www.newbornkingsmusic.com/index.html",
    facebook: "https://www.facebook.com/NewbornKINGSmusic/",
  },
  "nine deeez nite": {
    // Canonical spelling has 3 e's; calendar uses 2.
    website: "https://ninedeeeznite.com/",
    facebook: "https://www.facebook.com/ninedeeeznite/",
    instagram: "https://www.instagram.com/ninedeeeznite/",
    aliases: ["nine deez nite", "nine deeznite"],
  },
  "no standards": {
    website: "https://www.nostandardsband.com/",
    facebook: "https://www.facebook.com/NoStandardsBand/",
  },
  "no surrender": {
    website: "https://www.nosurrenderband.com/",
  },
  "not leaving sober": {
    website: "https://notleavingsober.wordpress.com/",
    facebook: "https://www.facebook.com/NotLeavingSober/",
  },
  "pam mccoy": {
    website: "https://pammccoysings.com/",
    facebook: "https://www.facebook.com/pammccoysings/",
    spotify: "https://open.spotify.com/artist/5nsSvElHGFZkk74NXN8B9Z",
  },
  "quincy mumford": {
    website: "https://www.quincymumford.com/",
  },
  "radio stranger": {
    website: "https://www.radiostrangerband.com/",
    facebook: "https://www.facebook.com/RadioStrangerBand",
    instagram: "https://www.instagram.com/radiostrangerband/",
  },
  "redbird flying solo": {
    website: "https://www.redbirdflyingsolo.com/",
    facebook: "https://www.facebook.com/redbirdflyingsolo/",
  },
  "rich and chad": {
    website: "https://richdmusic.com/",
    aliases: ["rich & chad"],
  },
  "rob connolly": {
    website: "https://robconnollymusic.com/",
    facebook: "https://www.facebook.com/RobConnollyMusic/",
    instagram: "https://www.instagram.com/robconnollymusic/",
  },
  "rockit fish": {
    // Calendar misspells as "Rocketfish"; canonical is "Rockit Fish".
    website: "https://rockitfishrocks.com/",
    facebook: "https://www.facebook.com/RockitFishRocks/",
    youtube: "https://www.youtube.com/channel/UCH-RDuHZwxhP4-TBsakMnIA",
    aliases: ["rocketfish", "rocket fish"],
  },
  "the rockets": {
    instagram: "https://www.instagram.com/rocketsband/",
    bandsintown: "https://www.bandsintown.com/a/124698-the-rockets",
  },
  "scott elk": {
    website: "https://www.scottelkmusic.com/",
  },
  "sherri pie": {
    website: "https://www.sherripie.com/",
    facebook: "https://www.facebook.com/musicsweetmusicfun/",
  },
  "smokin jackets": {
    website: "https://www.thesmokinjackets.com/",
    facebook: "https://www.facebook.com/thesmokinjackets/",
    instagram: "https://www.instagram.com/smokinjackets/",
    aliases: ["smoking jackets", "the smokin jackets"],
  },
  "soulshine": {
    website: "https://www.soulshineabb.com/",
  },
  "stretch & the armstrongs": {
    facebook: "https://www.facebook.com/satacoverbandnjnyc/",
    instagram: "https://www.instagram.com/stretchandthearmstrongs/",
    aliases: ["stretch and the armstrongs"],
  },
  "strumberry pie": {
    facebook: "https://www.facebook.com/StrumberryPie/",
    bandsintown: "https://www.bandsintown.com/a/4877075-strumberry-pie",
  },
  "suyat band": {
    website: "https://www.thesuyatband.com/",
  },
  "talking in cursive": {
    website: "https://www.talkingincursiveband.com/",
    facebook: "https://www.facebook.com/talkingincursiveband/",
    youtube: "https://www.youtube.com/channel/UCSJw1BCYdSp_1W6TkJinltw",
  },
  "the alt": {
    website: "https://thealtband.com/",
  },
  "the backbeat": {
    website: "http://www.thebackbeatmusic.com/",
    facebook: "https://www.facebook.com/TheBackbeatMusic/",
  },
  "the balanced breakfast band": {
    facebook: "https://www.facebook.com/TheBalancedBreakfastBand/",
  },
  "the benjamins": {
    website: "https://thebenjamins.net/",
    facebook: "https://www.facebook.com/thebenjaminsnj/",
    instagram: "https://www.instagram.com/thebenjaminsnj/",
    youtube: "https://www.youtube.com/user/thebenjaminsnj",
    spotify: "https://open.spotify.com/artist/1Y0hRtl21FgNwBR81H4L9a",
  },
  "the cliffs": {
    website: "https://thecliffsband.com/",
    facebook: "https://www.facebook.com/thecliffsband/",
    instagram: "https://www.instagram.com/thecliffsband/",
    bandsintown: "https://www.bandsintown.com/a/15463296-the-cliffs-band",
  },
  "the dogs": {
    facebook: "https://www.facebook.com/p/The-Dogs-Cover-Band-61554679425191/",
    instagram: "https://www.instagram.com/wearethedogsband/",
  },
  "the get down committee": {
    facebook: "https://www.facebook.com/thegetdowncommitteenj/",
  },
  "the haven": {
    website: "https://www.thehavenband.com/",
    facebook: "https://www.facebook.com/HavenBand/",
    bandsintown: "https://www.bandsintown.com/a/174830-the-haven",
    youtube: "https://www.youtube.com/@thehavenband8455",
  },
  "jo & the highland express": {
    // Calendar lists as "The Highland's Express".
    website: "https://joandthehighlandexpress.com/",
    facebook: "https://www.facebook.com/joandthehighlandexpress/",
    instagram: "https://www.instagram.com/joandthehighlandexpress/",
    youtube: "https://www.youtube.com/@Joandthehighlandexpress",
    aliases: ["the highland's express", "highland's express", "the highland express", "jo and the highland express"],
  },
  "the ned ryerson band": {
    website: "http://www.nedryersonlive.com/",
    facebook: "https://www.facebook.com/nedryersonband/",
    instagram: "https://www.instagram.com/nedryersonband/",
    aliases: ["ned ryerson band"],
  },
  "the nerds": {
    website: "https://www.the-nerds.com/",
    facebook: "https://www.facebook.com/thenerds/",
    instagram: "https://www.instagram.com/thenerdsband/",
  },
  "the polish nannies": {
    website: "https://www.thepolishnannies.com/",
    facebook: "https://www.facebook.com/Thepolishnannies",
    instagram: "https://www.instagram.com/polishnanniesnj/",
  },
  "the soulstirs": {
    facebook: "https://www.facebook.com/Soulstirsband/",
  },
  "tramps like us": {
    website: "https://www.trampslikeus.com/",
    facebook: "https://www.facebook.com/TrampsLikeUs/",
  },
  "ty mares": {
    website: "https://tymaresmusic.com/",
    facebook: "https://www.facebook.com/TyMaresmusic/",
  },
  "uncaged": {
    website: "http://zacbrownuncaged.com/",
    facebook: "https://www.facebook.com/uncagedzbb/",
    instagram: "https://www.instagram.com/zacbrownuncaged/",
    youtube: "https://www.youtube.com/@zacbrownuncaged",
    aliases: ["uncaged: a zac brown tribute", "uncaged a zac brown tribute"],
  },
  "undisputed": {
    website: "https://undisputedrocks.com/",
    facebook: "https://www.facebook.com/UndisputedNJ/",
    instagram: "https://www.instagram.com/undisputedbandnj/",
  },
  "vintage jamm": {
    website: "https://vintagejammusic.com/",
  },
  "vinyl traction": {
    website: "https://vinyltraction.com/",
  },
  "violet nova": {
    website: "https://m.violetnova.com/",
    facebook: "https://www.facebook.com/violetnovanj/",
  },
  "west end dogs": {
    website: "https://westenddogs.com/",
    facebook: "https://www.facebook.com/westenddogsband/",
  },
  "wheeland brothers": {
    website: "https://wheelandbrothers.com/",
    facebook: "https://www.facebook.com/wheelandbrothers/",
    instagram: "https://www.instagram.com/wheelandbrothers/",
    bandsintown: "https://www.bandsintown.com/a/1416561-wheeland-brothers",
  },
  "the dt's": {
    website: "https://thedtsmusic.com/",
    aliases: ["dt's", "the dts"],
  },
};

// Normalize for lookup: lowercase, drop punctuation, collapse whitespace.
function normalize(s: string): string {
  return (s || "")
    .toLowerCase()
    .replace(/[''`""]/g, "'")
    .replace(/&/g, "and")
    .replace(/[^a-z0-9 ]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

// Generate the set of name forms that should all map to the same entry.
// "Carl Gentry Solo" / "Carl Gentry Band" / "The Carl Gentry" → all match
// the entry keyed "carl gentry".
function variants(name: string): string[] {
  const base = normalize(name);
  const out = new Set<string>([base]);
  const stripThe = base.replace(/^the /, "");
  const stripSuffix = base.replace(/ (band|trio|duo|quartet|solo)$/i, "");
  out.add(stripThe);
  out.add(stripSuffix);
  out.add(stripThe.replace(/ (band|trio|duo|quartet|solo)$/i, ""));
  return Array.from(out).filter(Boolean);
}

export function findKnownBandLinks(bandName: string): KnownBandLinks | null {
  if (!bandName) return null;
  const wanted = variants(bandName);
  for (const [key, entry] of Object.entries(KNOWN)) {
    const candidates = [key, ...(entry.aliases || [])];
    for (const cand of candidates) {
      const candVariants = variants(cand);
      for (const w of wanted) {
        if (candVariants.includes(w)) return entry;
      }
    }
  }
  return null;
}
