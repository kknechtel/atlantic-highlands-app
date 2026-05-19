"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  listParcels,
  countParcels,
  getParcel,
  type ParcelListItem,
} from "@/lib/api";
import {
  MagnifyingGlassIcon,
  XMarkIcon,
  MapPinIcon,
  HomeIcon,
  BuildingOffice2Icon,
  Squares2X2Icon,
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

export default function ParcelsPage() {
  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [propertyClass, setPropertyClass] = useState("");
  const [minAssessment, setMinAssessment] = useState<string>("");
  const [page, setPage] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Debounce the search box so typing doesn't fire a request per keystroke.
  useEffect(() => {
    const t = setTimeout(() => {
      setDebouncedQ(q);
      setPage(0);
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  const queryParams = useMemo(
    () => ({
      q: debouncedQ || undefined,
      property_class: propertyClass || undefined,
      min_assessment: minAssessment ? Number(minAssessment) : undefined,
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
    }),
    [debouncedQ, propertyClass, minAssessment, page],
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
      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr className="text-left text-xs uppercase tracking-wider text-gray-500">
              <th className="px-4 py-2.5 font-medium">Block-Lot</th>
              <th className="px-4 py-2.5 font-medium">Address</th>
              <th className="px-4 py-2.5 font-medium">Class</th>
              <th className="px-4 py-2.5 font-medium text-right">Assessment</th>
              <th className="px-4 py-2.5 font-medium text-right">Last sale</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {isLoading ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                  Loading…
                </td>
              </tr>
            ) : !rows || rows.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                  No parcels match the current filters.
                </td>
              </tr>
            ) : (
              rows.map((p: ParcelListItem) => (
                <tr
                  key={p.id}
                  onClick={() => setSelectedId(p.id)}
                  className="hover:bg-gray-50 cursor-pointer"
                >
                  <td className="px-4 py-2 font-mono text-xs text-gray-700">
                    {p.block}-{p.lot}
                    {p.qualifier ? ` (${p.qualifier})` : ""}
                  </td>
                  <td className="px-4 py-2 text-gray-900">{p.property_location || "—"}</td>
                  <td className="px-4 py-2 text-gray-600">
                    <span className="inline-flex items-center gap-1 text-xs">
                      <span className="font-mono">{p.property_class || "?"}</span>
                      <span className="text-gray-400">·</span>
                      <span>{classLabel(p.property_class)}</span>
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right font-medium text-gray-900">
                    {fmtUSD(p.total_assessment)}
                  </td>
                  <td className="px-4 py-2 text-right text-gray-600">
                    {p.last_sale_date ? (
                      <span className="text-xs">
                        {fmtDate(p.last_sale_date)}
                        {p.last_sale_price ? ` · ${fmtUSD(p.last_sale_price)}` : ""}
                      </span>
                    ) : (
                      "—"
                    )}
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

  return (
    <div className="fixed inset-0 z-40 flex">
      {/* Backdrop */}
      <div className="flex-1 bg-black/30" onClick={onClose} />
      {/* Panel */}
      <aside className="w-full max-w-md bg-white border-l border-gray-200 shadow-xl overflow-y-auto">
        <div className="px-5 py-4 border-b border-gray-200 flex items-start justify-between">
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
            <Section icon={Squares2X2Icon} title="Identity">
              <Row label="PAMS PIN" value={data.pams_pin} mono />
              <Row label="County / Muni" value={`${data.county_code} / ${data.muni_code}`} />
              <Row label="Property class" value={`${data.property_class || "?"} — ${classLabel(data.property_class)}`} />
              <Row label="Zoning" value={data.zoning} />
              <Row label="Lot size" value={data.lot_size_acres ? `${data.lot_size_acres.toFixed(2)} ac` : null} />
            </Section>

            <Section icon={HomeIcon} title="Building">
              <Row label="Year built" value={data.year_built} />
              <Row label="Living sqft" value={data.living_sqft?.toLocaleString()} />
            </Section>

            <Section icon={BuildingOffice2Icon} title="Owner (mailing address)">
              <Row label="Name" value={data.owner_name || <em className="text-gray-400">not in NJGIN composite</em>} />
              <Row label="Street" value={data.owner_street} />
              <Row label="City / State / ZIP" value={data.owner_city_state_zip} />
            </Section>

            <Section title="Assessment">
              <Row label="Year" value={data.assessment_year} />
              <Row label="Land" value={fmtUSD(data.land_value)} />
              <Row label="Improvements" value={fmtUSD(data.improvement_value)} />
              <Row label="Exemption" value={fmtUSD(data.exemption_value)} />
              <Row label="Total" value={fmtUSD(data.total_assessment)} bold />
              <Row label="Tax (last yr)" value={fmtUSD(data.tax_amount)} />
            </Section>

            <Section title="Last sale">
              <Row label="Date" value={fmtDate(data.last_sale_date)} />
              <Row label="Price" value={fmtUSD(data.last_sale_price)} bold />
              <Row label="Deed (book / page)" value={
                data.last_sale_book && data.last_sale_page
                  ? `${data.last_sale_book} / ${data.last_sale_page}`
                  : null
              } mono />
              <Row label="NU code" value={data.last_sale_nu_code || <em className="text-gray-400">(arms-length)</em>} mono />
            </Section>

            {data.data_source && (
              <p className="text-[11px] text-gray-400 pt-2 border-t border-gray-100">
                Source: {data.data_source}
              </p>
            )}
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
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
  bold?: boolean;
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
        {isEmpty ? "—" : value}
      </dd>
    </div>
  );
}
