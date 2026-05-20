"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  listParcels,
  countParcels,
  getParcel,
  type ParcelListItem,
  type ParcelSortColumn,
} from "@/lib/api";
import {
  MagnifyingGlassIcon,
  XMarkIcon,
  MapPinIcon,
  HomeIcon,
  BuildingOffice2Icon,
  Squares2X2Icon,
  ChevronUpIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  ArrowTopRightOnSquareIcon,
  InformationCircleIcon,
} from "@heroicons/react/24/outline";

const brandColor = "#385854";

// NJ MOD-IV property classes (the codes the borough assessor files with the
// county). Vacant/residential/commercial/exempt are the only ones that show
// up in Atlantic Highlands; included a few extras for forward compatibility.
const CLASS_LABELS: Record<string, string> = {
  "1": "Vacant land",
  "2": "Residential",
  "3A": "Farm (regular)",
  "3B": "Farm (qualified)",
  "4A": "Commercial",
  "4B": "Industrial",
  "4C": "Apartment (5+)",
  "5A": "Railroad",
  "15A": "Public school",
  "15B": "Other school",
  "15C": "Public property",
  "15D": "Church/charitable",
  "15E": "Cemetery",
  "15F": "Other exempt",
};

const PAGE_SIZE = 100;

function classLabel(code: string | null | undefined): string {
  if (!code) return "—";
  return CLASS_LABELS[code] ?? code;
}

function fmtUSD(n: number | null | undefined): string {
  if (n == null) return "—";
  return n.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
}

function fmtDate(s: string | null | undefined): string {
  if (!s) return "—";
  return s.slice(0, 10);
}

function fmtNum(n: number | null | undefined, digits = 2): string {
  if (n == null) return "—";
  return n.toLocaleString("en-US", { maximumFractionDigits: digits });
}

function yearsSince(dateStr: string | null | undefined): number | null {
  if (!dateStr) return null;
  const sold = new Date(dateStr);
  if (isNaN(sold.getTime())) return null;
  return (Date.now() - sold.getTime()) / (365.25 * 24 * 3600 * 1000);
}

/**
 * Parse NJGIN's BLDG_DESC field. The string format encodes floor + unit
 * makeup, e.g.:
 *   "1STFLR-3/1/1"   = 1st floor, 3 bedrooms / 1 bath / 1 garage
 *   "2NDFLR-4/2/1"   = 2nd floor, 4BR / 2BA / 1 garage
 *   "CONDO"          = generic condo, no breakdown
 * Returns null if it doesn't match the pattern so the caller can fall back
 * to showing the raw string.
 */
function parseBuildingDescription(desc: string | null | undefined): {
  floor: string;
  bedrooms: number;
  bathrooms: number;
  garage: number;
} | null {
  if (!desc) return null;
  const m = desc.match(/^(\d+(?:ST|ND|RD|TH)FLR)-(\d+)\/(\d+)\/(\d+)$/i);
  if (!m) return null;
  return {
    floor: m[1].toUpperCase(),
    bedrooms: parseInt(m[2], 10),
    bathrooms: parseInt(m[3], 10),
    garage: parseInt(m[4], 10),
  };
}

/**
 * Parse NJGIN's LAND_DESC field. Most common formats:
 *   "50X130"            -> 50 by 130 (frontage x depth in feet)
 *   "C.E.=.90098%"      -> condominium equity share (percent ownership)
 * Returns null if it's neither shape — caller falls back to raw string.
 */
function parseLandDescription(desc: string | null | undefined):
  | { kind: "dimensions"; width: number; depth: number }
  | { kind: "condo_equity"; pct: number }
  | null {
  if (!desc) return null;
  const dim = desc.match(/^(\d+)\s*[Xx]\s*(\d+)$/);
  if (dim) return { kind: "dimensions", width: parseInt(dim[1]), depth: parseInt(dim[2]) };
  const ce = desc.match(/^C\.E\.\s*=\s*\.?(\d+(?:\.\d+)?)\s*%?$/i);
  if (ce) {
    const raw = parseFloat(ce[1]);
    // Sometimes the value is stored as e.g. ".90098" meaning 0.90098%; other
    // times as "90098" meaning the same. Heuristic: if > 5 it's already a
    // decimal-shifted percent string; if <= 5 it's a "0.x" decimal.
    const pct = raw > 5 ? raw / 100000 : raw;
    return { kind: "condo_equity", pct };
  }
  return null;
}

/**
 * Build a Zillow deep-link by address. Zillow's `/homes/{q}_rb/` path is a
 * documented redirect that lands on the property page when they can match
 * the address — for ambiguous cases it falls back to search results, which
 * is still useful. Atlantic Highlands has two ZIPs (07716 majority, 07738
 * sliver); we use the bordering ZIP from MOD-IV when available, otherwise
 * leave the borough name to disambiguate.
 */
function zillowUrl(address: string | null): string | null {
  if (!address) return null;
  const q = `${address}, Atlantic Highlands, NJ`.replace(/\s+/g, "-");
  return `https://www.zillow.com/homes/${encodeURIComponent(q)}_rb/`;
}

function realtorUrl(address: string | null): string | null {
  if (!address) return null;
  const q = `${address}, Atlantic Highlands, NJ`;
  return `https://www.realtor.com/realestateandhomes-search/${encodeURIComponent(q)}`;
}

function googleMapsUrl(address: string | null): string | null {
  if (!address) return null;
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(
    `${address}, Atlantic Highlands, NJ`,
  )}`;
}

function googleStreetViewUrl(address: string | null): string | null {
  if (!address) return null;
  return `https://www.google.com/maps?layer=c&q=${encodeURIComponent(
    `${address}, Atlantic Highlands, NJ`,
  )}`;
}

/**
 * Classic Google Maps embed iframe URL. This is the only Maps embed that
 * doesn't require an API key — Google's documented Embed API (`/maps/embed`)
 * does. `layer=c` overlays the Street View "pegman" UI so the user can drop
 * into Street View *inside* the iframe without leaving the app. Atlantic
 * Highlands has tight street density so a default zoom of 17 keeps the
 * parcel + its 3-4 neighbors visible.
 */
function googleMapsEmbedUrl(address: string | null): string | null {
  if (!address) return null;
  return `https://maps.google.com/maps?q=${encodeURIComponent(
    `${address}, Atlantic Highlands, NJ`,
  )}&z=17&layer=c&output=embed`;
}

interface SortableHeaderProps {
  label: string;
  column: ParcelSortColumn;
  sortBy: ParcelSortColumn;
  sortDir: "asc" | "desc";
  onSort: (column: ParcelSortColumn) => void;
  align?: "left" | "right";
}

function SortableHeader({ label, column, sortBy, sortDir, onSort, align = "left" }: SortableHeaderProps) {
  const active = sortBy === column;
  return (
    <th
      onClick={() => onSort(column)}
      className={`px-4 py-2.5 font-medium select-none cursor-pointer hover:text-gray-700 ${
        align === "right" ? "text-right" : ""
      } ${active ? "text-gray-900" : ""}`}
    >
      <span className={`inline-flex items-center gap-0.5 ${align === "right" ? "flex-row-reverse" : ""}`}>
        {label}
        {active ? (
          sortDir === "asc" ? (
            <ChevronUpIcon className="w-3 h-3" />
          ) : (
            <ChevronDownIcon className="w-3 h-3" />
          )
        ) : (
          <span className="w-3 h-3" />
        )}
      </span>
    </th>
  );
}

export default function ParcelsPage() {
  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [propertyClass, setPropertyClass] = useState("");
  const [minAssessment, setMinAssessment] = useState<string>("");
  const [page, setPage] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<ParcelSortColumn>("block_lot");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  // Debounce the search box so typing doesn't fire a request per keystroke.
  useEffect(() => {
    const t = setTimeout(() => {
      setDebouncedQ(q);
      setPage(0);
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  const toggleSort = (col: ParcelSortColumn) => {
    if (col === sortBy) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(col);
      // First click on a numeric/date column usually wants "biggest/newest first";
      // alpha columns want A→Z. Heuristic matches the user's likely intent.
      setSortDir(
        col === "total_assessment" ||
          col === "tax_amount" ||
          col === "lot_size_acres" ||
          col === "year_built" ||
          col === "last_sale_price" ||
          col === "last_sale_date"
          ? "desc"
          : "asc",
      );
    }
    setPage(0);
  };

  const queryParams = useMemo(
    () => ({
      q: debouncedQ || undefined,
      property_class: propertyClass || undefined,
      min_assessment: minAssessment ? Number(minAssessment) : undefined,
      sort_by: sortBy,
      sort_dir: sortDir,
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
    }),
    [debouncedQ, propertyClass, minAssessment, sortBy, sortDir, page],
  );

  const { data: rows, isLoading } = useQuery({
    queryKey: ["parcels", queryParams],
    queryFn: () => listParcels(queryParams),
  });

  const { data: countData } = useQuery({
    queryKey: ["parcels-count"],
    queryFn: countParcels,
    staleTime: 60_000,
  });

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-baseline justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Property &amp; Tax Records</h1>
          <p className="text-sm text-gray-500 mt-1">
            NJ MOD-IV parcels for Atlantic Highlands borough
            {countData ? (
              <>
                {" "}— <span className="font-medium">{countData.count.toLocaleString()}</span> parcels
              </>
            ) : null}
            . Click a row for details.
          </p>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white border border-gray-200 rounded-lg p-4 mb-4 flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-[240px]">
          <MagnifyingGlassIcon className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search address, owner, or block-lot…"
            className="w-full pl-9 pr-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-offset-1"
            style={{ outlineColor: brandColor }}
          />
        </div>
        <select
          value={propertyClass}
          onChange={(e) => {
            setPropertyClass(e.target.value);
            setPage(0);
          }}
          className="px-3 py-2 border border-gray-300 rounded-md text-sm bg-white"
        >
          <option value="">All classes</option>
          {Object.entries(CLASS_LABELS).map(([code, label]) => (
            <option key={code} value={code}>
              {code} — {label}
            </option>
          ))}
        </select>
        <input
          type="number"
          value={minAssessment}
          onChange={(e) => {
            setMinAssessment(e.target.value);
            setPage(0);
          }}
          placeholder="Min assessment ($)"
          className="px-3 py-2 border border-gray-300 rounded-md text-sm w-44"
        />
        {(debouncedQ || propertyClass || minAssessment) && (
          <button
            onClick={() => {
              setQ("");
              setPropertyClass("");
              setMinAssessment("");
            }}
            className="px-3 py-2 text-sm text-gray-600 hover:text-gray-900"
          >
            Clear
          </button>
        )}
      </div>

      {/* Table */}
      <div className="bg-white border border-gray-200 rounded-lg overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr className="text-left text-xs uppercase tracking-wider text-gray-500">
              <SortableHeader label="Block-Lot" column="block_lot" sortBy={sortBy} sortDir={sortDir} onSort={toggleSort} />
              <SortableHeader label="Address" column="property_location" sortBy={sortBy} sortDir={sortDir} onSort={toggleSort} />
              <SortableHeader label="Class" column="property_class" sortBy={sortBy} sortDir={sortDir} onSort={toggleSort} />
              <SortableHeader label="Acres" column="lot_size_acres" sortBy={sortBy} sortDir={sortDir} onSort={toggleSort} align="right" />
              <SortableHeader label="Built" column="year_built" sortBy={sortBy} sortDir={sortDir} onSort={toggleSort} align="right" />
              <SortableHeader label="Assessment" column="total_assessment" sortBy={sortBy} sortDir={sortDir} onSort={toggleSort} align="right" />
              <SortableHeader label="Tax" column="tax_amount" sortBy={sortBy} sortDir={sortDir} onSort={toggleSort} align="right" />
              <SortableHeader label="Last sale" column="last_sale_date" sortBy={sortBy} sortDir={sortDir} onSort={toggleSort} align="right" />
              <th className="w-8" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {isLoading ? (
              <tr>
                <td colSpan={9} className="px-4 py-8 text-center text-gray-400">
                  Loading…
                </td>
              </tr>
            ) : !rows || rows.length === 0 ? (
              <tr>
                <td colSpan={9} className="px-4 py-8 text-center text-gray-400">
                  No parcels match the current filters.
                </td>
              </tr>
            ) : (
              rows.map((p: ParcelListItem) => (
                <tr
                  key={p.id}
                  onClick={() => setSelectedId(p.id)}
                  className="hover:bg-gray-50 cursor-pointer group"
                  title="Click for details"
                >
                  <td className="px-4 py-2 font-mono text-xs text-gray-700 whitespace-nowrap">
                    {p.block}-{p.lot}
                    {p.qualifier ? <span className="text-gray-400"> ({p.qualifier})</span> : null}
                  </td>
                  <td className="px-4 py-2 text-gray-900">{p.property_location || "—"}</td>
                  <td className="px-4 py-2 text-gray-600 whitespace-nowrap">
                    <span className="inline-flex items-center gap-1 text-xs">
                      <span className="font-mono">{p.property_class || "?"}</span>
                      <span className="text-gray-400">·</span>
                      <span>{classLabel(p.property_class)}</span>
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right text-gray-700 tabular-nums whitespace-nowrap">
                    {p.lot_size_acres != null ? fmtNum(p.lot_size_acres) : "—"}
                  </td>
                  <td className="px-4 py-2 text-right text-gray-700 tabular-nums whitespace-nowrap">
                    {p.year_built || "—"}
                  </td>
                  <td className="px-4 py-2 text-right font-medium text-gray-900 tabular-nums whitespace-nowrap">
                    {fmtUSD(p.total_assessment)}
                  </td>
                  <td className="px-4 py-2 text-right text-gray-600 tabular-nums whitespace-nowrap">
                    {fmtUSD(p.tax_amount)}
                  </td>
                  <td className="px-4 py-2 text-right text-gray-600 whitespace-nowrap">
                    {p.last_sale_date || p.last_sale_price ? (
                      <span className="text-xs">
                        {p.last_sale_date ? fmtDate(p.last_sale_date) : ""}
                        {p.last_sale_date && p.last_sale_price ? " · " : ""}
                        {p.last_sale_price ? fmtUSD(p.last_sale_price) : ""}
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="px-2 py-2 text-gray-300 group-hover:text-gray-600">
                    <ChevronRightIcon className="w-4 h-4" />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>

        {/* Pagination */}
        <div className="px-4 py-3 border-t border-gray-200 flex items-center justify-between text-sm">
          <span className="text-gray-500">
            Showing rows {rows && rows.length > 0 ? page * PAGE_SIZE + 1 : 0}
            {rows && rows.length > 0 ? `–${page * PAGE_SIZE + rows.length}` : ""}
            {countData ? ` of ${countData.count.toLocaleString()}` : ""}
          </span>
          <div className="flex gap-2">
            <button
              disabled={page === 0}
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              className="px-3 py-1.5 text-sm border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Previous
            </button>
            <button
              disabled={!rows || rows.length < PAGE_SIZE}
              onClick={() => setPage((p) => p + 1)}
              className="px-3 py-1.5 text-sm border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Next
            </button>
          </div>
        </div>
      </div>

      {selectedId && (
        <ParcelDrawer id={selectedId} onClose={() => setSelectedId(null)} />
      )}
    </div>
  );
}

function ParcelDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const { data, isLoading } = useQuery({
    queryKey: ["parcel", id],
    queryFn: () => getParcel(id),
  });

  const yrsSinceSale = data ? yearsSince(data.last_sale_date) : null;
  const landShare =
    data && data.land_value && data.total_assessment
      ? (data.land_value / data.total_assessment) * 100
      : null;
  const apprAnnualPct =
    data && data.last_sale_price && data.total_assessment && yrsSinceSale && yrsSinceSale > 0
      ? (Math.pow(data.total_assessment / data.last_sale_price, 1 / yrsSinceSale) - 1) * 100
      : null;
  const pricePerSqft =
    data && data.last_sale_price && data.living_sqft
      ? data.last_sale_price / data.living_sqft
      : null;

  const addr = data?.property_location || null;
  const zUrl = zillowUrl(addr);
  const rUrl = realtorUrl(addr);
  const gmUrl = googleMapsUrl(addr);
  const svUrl = googleStreetViewUrl(addr);
  const embedUrl = googleMapsEmbedUrl(addr);

  return (
    <div className="fixed inset-0 z-40 flex">
      <div className="flex-1 bg-black/30" onClick={onClose} />
      <aside className="w-full max-w-lg bg-white border-l border-gray-200 shadow-xl overflow-y-auto">
        <div className="px-5 py-4 border-b border-gray-200 flex items-start justify-between sticky top-0 bg-white z-10">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">
              {data ? `Block ${data.block}, Lot ${data.lot}` : "Parcel"}
              {data?.qualifier ? <span className="text-gray-500 font-normal"> ({data.qualifier})</span> : null}
            </h2>
            {data?.property_location && (
              <p className="text-sm text-gray-600 mt-0.5 flex items-center gap-1">
                <MapPinIcon className="w-4 h-4 text-gray-400" />
                {data.property_location}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-md hover:bg-gray-100 text-gray-500"
          >
            <XMarkIcon className="w-5 h-5" />
          </button>
        </div>

        {isLoading || !data ? (
          <div className="p-6 text-center text-gray-400">Loading…</div>
        ) : (
          <div className="p-5 space-y-5">
            {/* Embedded map — Google's classic embed (no API key required) */}
            {embedUrl && (
              <div className="rounded-md overflow-hidden border border-gray-200">
                <iframe
                  src={embedUrl}
                  width="100%"
                  height="200"
                  loading="lazy"
                  referrerPolicy="no-referrer-when-downgrade"
                  title="Parcel location"
                  className="block"
                />
              </div>
            )}

            {/* External links — Zillow blocks iframe embedding via X-Frame-Options
                so we link out. NJ Property Records and Google Street View give
                you photos, sale history, and the actual streetscape. */}
            {addr && (
              <Section title="External lookup">
                <div className="grid grid-cols-2 gap-2 p-2">
                  <ExternalLinkButton href={zUrl} label="Zillow" />
                  <ExternalLinkButton href={rUrl} label="Realtor.com" />
                  <ExternalLinkButton href={svUrl} label="Street View" />
                  <ExternalLinkButton href={gmUrl} label="Google Maps" />
                </div>
              </Section>
            )}

            <Section icon={Squares2X2Icon} title="Identity">
              <Row label="PAMS PIN" value={data.pams_pin} mono />
              <Row label="County / Muni" value={`${data.county_code} / ${data.muni_code}`} />
              <Row label="Property class" value={`${data.property_class || "?"} — ${classLabel(data.property_class)}`} />
              <Row label="Property use" value={data.property_use} hint={!data.property_use ? "not on file" : undefined} mono />
              <Row label="Zoning" value={data.zoning} hint={!data.zoning ? "not in NJGIN layer" : undefined} />
            </Section>

            <Section icon={HomeIcon} title="Building">
              <Row label="Year built" value={data.year_built} />
              <Row label="Class code" value={data.building_class} hint={!data.building_class ? "no class on file" : "NJ assessor building class"} mono />
              {(() => {
                const parsed = parseBuildingDescription(data.building_description);
                if (parsed) {
                  return (
                    <>
                      <Row label="Floor" value={parsed.floor} />
                      <Row label="Bedrooms / Baths" value={`${parsed.bedrooms} BR / ${parsed.bathrooms} BA`} />
                      <Row label="Garage" value={parsed.garage ? `${parsed.garage} space${parsed.garage > 1 ? "s" : ""}` : "—"} />
                    </>
                  );
                }
                return <Row label="Description" value={data.building_description} hint={!data.building_description ? "no description (typical for single-family)" : undefined} mono />;
              })()}
              <Row label="Dwelling units" value={data.dwelling_units} />
              <Row
                label="Living sqft"
                value={data.living_sqft?.toLocaleString()}
                hint={!data.living_sqft ? "not in MOD-IV — requires assessor OPRA" : undefined}
              />
            </Section>

            <Section title="Land">
              <Row label="Lot size" value={data.lot_size_acres ? `${data.lot_size_acres.toFixed(2)} ac` : null} />
              {(() => {
                const parsed = parseLandDescription(data.land_description);
                if (parsed?.kind === "dimensions") {
                  return <Row label="Dimensions" value={`${parsed.width} × ${parsed.depth} ft`} />;
                }
                if (parsed?.kind === "condo_equity") {
                  return <Row label="Condo equity share" value={`${parsed.pct.toFixed(4)}%`} />;
                }
                return <Row label="Description" value={data.land_description} hint={!data.land_description ? "not provided" : undefined} mono />;
              })()}
              <Row label="ZIP" value={data.zip5} mono />
            </Section>

            <Section icon={BuildingOffice2Icon} title="Owner (mailing address)">
              <Row
                label="Name"
                value={data.owner_name}
                hint={!data.owner_name ? "scrubbed by NJGIN composite" : undefined}
              />
              <Row label="Street" value={data.owner_street} />
              <Row label="City / State / ZIP" value={data.owner_city_state_zip} />
            </Section>

            <Section title="Assessment">
              <Row label="Year" value={data.assessment_year} hint={!data.assessment_year ? "not in layer" : undefined} />
              <Row label="Land" value={fmtUSD(data.land_value)} />
              <Row label="Improvements" value={fmtUSD(data.improvement_value)} />
              <Row label="Exemption" value={data.exemption_value ? fmtUSD(data.exemption_value) : "$0"} />
              <Row label="Total" value={fmtUSD(data.total_assessment)} bold />
              <Row label="Tax (last yr)" value={fmtUSD(data.tax_amount)} />
              {landShare != null && (
                <Row label="Land share" value={`${landShare.toFixed(0)}% of assessment`} />
              )}
            </Section>

            <Section title="Last sale">
              <Row label="Date" value={fmtDate(data.last_sale_date)} />
              <Row label="Price" value={fmtUSD(data.last_sale_price)} bold />
              {yrsSinceSale != null && (
                <Row label="Years since sale" value={yrsSinceSale.toFixed(1)} />
              )}
              {apprAnnualPct != null && (
                <Row
                  label="Implied appreciation"
                  value={`${apprAnnualPct.toFixed(1)}% / yr (sale → today's assessment)`}
                />
              )}
              {pricePerSqft != null && (
                <Row label="Sale $/sqft" value={fmtUSD(pricePerSqft)} />
              )}
              <Row
                label="Deed (book / page)"
                value={
                  data.last_sale_book && data.last_sale_page
                    ? `${data.last_sale_book} / ${data.last_sale_page}`
                    : null
                }
                mono
              />
              <Row
                label="NU code"
                value={data.last_sale_nu_code}
                hint={!data.last_sale_nu_code ? "blank = arms-length sale" : undefined}
                mono
              />
            </Section>

            <div className="border-t border-gray-100 pt-3 text-[11px] text-gray-400 space-y-1">
              <div className="flex items-start gap-1.5">
                <InformationCircleIcon className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                <p>
                  Source: NJGIN MOD-IV composite. Owner names, sqft, zoning, and
                  assessment year are not exposed by this layer — fill from the
                  full NJ DCA MOD-IV file or use the external links above.
                </p>
              </div>
              {data.data_source && <p className="pl-5">Ingested as: {data.data_source}</p>}
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}

function Section({
  icon: Icon,
  title,
  children,
}: {
  icon?: any;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2 flex items-center gap-1.5">
        {Icon ? <Icon className="w-3.5 h-3.5" /> : null}
        {title}
      </h3>
      <dl className="divide-y divide-gray-100 border border-gray-200 rounded-md">{children}</dl>
    </div>
  );
}

function Row({
  label,
  value,
  mono,
  bold,
  hint,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
  bold?: boolean;
  hint?: string;
}) {
  const isEmpty = value == null || value === "" || value === "—";
  return (
    <div className="flex justify-between gap-3 px-3 py-1.5 text-sm">
      <dt className="text-gray-500 flex-shrink-0">{label}</dt>
      <dd
        className={`${mono ? "font-mono text-xs" : ""} ${bold ? "font-semibold text-gray-900" : "text-gray-700"} ${
          isEmpty ? "text-gray-400" : ""
        } text-right break-words`}
      >
        {isEmpty ? (
          hint ? <em className="text-gray-400 not-italic text-xs">{hint}</em> : "—"
        ) : (
          value
        )}
      </dd>
    </div>
  );
}

function ExternalLinkButton({ href, label }: { href: string | null; label: string }) {
  if (!href) return null;
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="flex items-center justify-between gap-2 px-3 py-2 text-sm border border-gray-200 rounded-md hover:bg-gray-50 hover:border-gray-300 text-gray-700 transition-colors"
    >
      <span>{label}</span>
      <ArrowTopRightOnSquareIcon className="w-3.5 h-3.5 text-gray-400" />
    </a>
  );
}
