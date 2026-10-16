/**
 * The town this build serves, from municipalities/<slug>/profile.json
 * (inlined at build time by next.config.js). Use TOWN instead of writing a
 * town's name, address, colors or map position into a component.
 */

export interface MunicipalityEntity {
  id: string;
  label: string;
  short: string;
  kind: "town" | "school" | "regional" | "state" | string;
  primary?: boolean;
  note?: string;
  fiscal_year?: string;
  /** Short acronym used in labels, e.g. "HHRSD". Falls back to `short`. */
  abbr?: string;
  aliases?: string[];
}

export interface OpraAgency {
  agency_name: string;
  abbr: string;
  address_line: string;
  phone: string;
  fax?: string;
  email: string;
  custodian_name: string;
  custodian_title: string;
  submission_note: string;
  govpilot_url?: string;
  form_url?: string;
}

export interface Municipality {
  slug: string;
  name: string;
  official_name: string;
  short_name: string;
  kind: string;
  state: string;
  state_name: string;
  county: string;
  timezone: string;
  site_name: string;
  site_url: string;
  contact_email: string;
  official_site: string;
  town_hall: { name: string; address: string };
  map: { center: [number, number]; zoom: number };
  brand_color: string;
  /** Alt text for public/dashboard-banner.jpg. */
  banner_alt?: string;
  /** Towns the community events app covers, this town first. */
  events_area?: string[];
  fiscal_year: string;
  /** One-paragraph descriptions shown on overview pages. */
  about?: {
    town?: string;
    school?: string;
    /** Caveat shown under school financial dashboards (e.g. a district consolidation). */
    school_finance_note?: string;
    /** Caveat shown under school year-over-year trend charts. */
    school_trend_note?: string;
  };
  entities: MunicipalityEntity[];
  opra?: { portal_label: string; agencies: { borough: OpraAgency; school: OpraAgency } };
}

export const TOWN: Municipality = JSON.parse(process.env.NEXT_PUBLIC_MUNICIPALITY || "{}");

/** "Atlantic Highlands, NJ" */
export const PLACE = `${TOWN.name}, ${TOWN.state}`;

export const PRIMARY_ENTITY: MunicipalityEntity =
  TOWN.entities?.find((e) => e.primary) ?? TOWN.entities?.[0] ?? {
    id: "town",
    label: TOWN.official_name,
    short: TOWN.name,
    kind: "town",
  };

export function entityById(id: string | null | undefined): MunicipalityEntity | undefined {
  return TOWN.entities?.find((e) => e.id === id);
}

export function entityOfKind(kind: string): MunicipalityEntity | undefined {
  return TOWN.entities?.find((e) => e.kind === kind);
}

/** The town's school district entity (first entity of kind "school"). */
export const SCHOOL_ENTITY: MunicipalityEntity = entityOfKind("school") ?? {
  id: "school",
  label: "School District",
  short: "School District",
  kind: "school",
};

/** Acronym for the school district in UI labels, e.g. "HHRSD". */
export const SCHOOL_ABBR = SCHOOL_ENTITY.abbr ?? SCHOOL_ENTITY.short;

/** "ahnj.info" */
export const SITE_HOST = (() => {
  try {
    return new URL(TOWN.site_url).host;
  } catch {
    return "";
  }
})();

/** The community events app lives on the events. subdomain of the site. */
export const EVENTS_HOST = `events.${SITE_HOST}`;
export const EVENTS_URL = `https://${EVENTS_HOST}`;

/** Lowercase prefix for downloaded file names, e.g. "ah". */
export const FILE_PREFIX = (TOWN.short_name || TOWN.slug || "town").toLowerCase();

/** Towns the events app covers, e.g. ["Atlantic Highlands", "Highlands", "Sea Bright"]. */
export const EVENTS_AREA: string[] = TOWN.events_area?.length ? TOWN.events_area : [TOWN.name];

/** ["A", "B", "C"] -> "A, B, and C" */
export function listPhrase(items: string[]): string {
  if (items.length <= 2) return items.join(" and ");
  return `${items.slice(0, -1).join(", ")}, and ${items[items.length - 1]}`;
}

/** "Borough", "Township", "City"... */
export const KIND_LABEL = TOWN.kind ? TOWN.kind.charAt(0).toUpperCase() + TOWN.kind.slice(1) : "Town";

/** "Monmouth" for "Monmouth County". */
export const COUNTY_SHORT = (TOWN.county || "").replace(/\s+County$/i, "");

/** "ahnj.com" - host of the town's official website, without www. */
export const OFFICIAL_HOST = (() => {
  try {
    return new URL(TOWN.official_site).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
})();
