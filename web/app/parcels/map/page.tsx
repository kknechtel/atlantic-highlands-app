"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import dynamic from "next/dynamic";
import Link from "next/link";
import {
  ListBulletIcon,
  XMarkIcon,
  MapPinIcon,
  ArrowTopRightOnSquareIcon,
} from "@heroicons/react/24/outline";
import { getAuthToken } from "@/lib/api";
import "leaflet/dist/leaflet.css";

const brandColor = "#385854";

// react-leaflet touches the DOM at import time (Leaflet looks for window /
// document); rendering it server-side throws. Dynamic-import the wrapper
// with ssr:false so it only loads in the browser.
const ParcelMap = dynamic(() => import("@/components/ParcelMap"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-full text-gray-400">
      Loading map…
    </div>
  ),
});

interface ParcelFeatureProps {
  block: string;
  lot: string;
  qualifier: string;
  address: string | null;
  property_class: string | null;
  total_assessment: number | null;
  tax_amount: number | null;
  year_built: number | null;
}

export interface ParcelFeature {
  type: "Feature";
  id: string;
  properties: ParcelFeatureProps;
  geometry: GeoJSON.Polygon;
}

export interface ParcelFC {
  type: "FeatureCollection";
  features: ParcelFeature[];
}

// Color ramp for the chloropleth. Five quantile bins: low to high assessment.
// Picked to read as a clear gradient on top of OSM tiles (which are pastel).
const ASSESSMENT_COLORS = ["#dcdcdc", "#fde68a", "#fbbf24", "#f97316", "#dc2626"];

function pickBins(values: number[]): number[] {
  // Quantile boundaries at 20/40/60/80%. Values come in sorted (we sort the
  // input). Skip zeros and nulls since they distort the lower quantile.
  const xs = values.filter((v) => v > 0).slice().sort((a, b) => a - b);
  if (xs.length === 0) return [0, 0, 0, 0];
  return [0.2, 0.4, 0.6, 0.8].map((q) => xs[Math.floor(xs.length * q)]);
}

export default function ParcelMapPage() {
  const [selected, setSelected] = useState<ParcelFeature | null>(null);
  const [propertyClass, setPropertyClass] = useState("");

  const { data, isLoading } = useQuery<ParcelFC>({
    queryKey: ["parcels-geojson", propertyClass],
    queryFn: async () => {
      const qs = new URLSearchParams();
      if (propertyClass) qs.set("property_class", propertyClass);
      const url = `/api/parcels/geojson${qs.toString() ? `?${qs}` : ""}`;
      const res = await fetch(url, { headers: getAuthToken() });
      if (!res.ok) throw new Error(`GeoJSON fetch failed: ${res.status}`);
      return res.json();
    },
  });

  const bins = useMemo(() => {
    if (!data?.features) return [0, 0, 0, 0];
    return pickBins(data.features.map((f) => f.properties.total_assessment ?? 0));
  }, [data]);

  return (
    <div className="flex flex-col h-screen">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200 bg-white">
        <div>
          <h1 className="text-lg font-semibold text-gray-900">Property &amp; Tax Map</h1>
          <p className="text-xs text-gray-500">
            {data?.features.length.toLocaleString() ?? "…"} parcels · colored by total assessment
          </p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={propertyClass}
            onChange={(e) => setPropertyClass(e.target.value)}
            className="px-3 py-1.5 border border-gray-300 rounded-md text-sm bg-white"
          >
            <option value="">All classes</option>
            <option value="1">1 — Vacant land</option>
            <option value="2">2 — Residential</option>
            <option value="4A">4A — Commercial</option>
            <option value="4B">4B — Industrial</option>
            <option value="4C">4C — Apartment (5+)</option>
            <option value="15C">15C — Public property</option>
            <option value="15D">15D — Church/charitable</option>
            <option value="15F">15F — Other exempt</option>
          </select>
          <Link
            href="/parcels"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm border border-gray-300 rounded-md hover:bg-gray-50"
          >
            <ListBulletIcon className="w-4 h-4" />
            Table view
          </Link>
        </div>
      </div>

      {/* Legend */}
      <Legend bins={bins} />

      {/* Map */}
      <div className="flex-1 relative">
        {isLoading ? (
          <div className="flex items-center justify-center h-full text-gray-400">
            Loading parcels…
          </div>
        ) : data ? (
          <ParcelMap features={data.features} bins={bins} colors={ASSESSMENT_COLORS} onSelect={setSelected} />
        ) : (
          <div className="flex items-center justify-center h-full text-gray-400">No data.</div>
        )}

        {selected && <SelectionCard feature={selected} onClose={() => setSelected(null)} />}
      </div>
    </div>
  );
}

function Legend({ bins }: { bins: number[] }) {
  if (bins.every((b) => b === 0)) return null;
  const fmt = (n: number) =>
    n >= 1_000_000 ? `$${(n / 1_000_000).toFixed(1)}M` : `$${Math.round(n / 1000)}k`;
  const labels = [
    `< ${fmt(bins[0])}`,
    `${fmt(bins[0])}–${fmt(bins[1])}`,
    `${fmt(bins[1])}–${fmt(bins[2])}`,
    `${fmt(bins[2])}–${fmt(bins[3])}`,
    `≥ ${fmt(bins[3])}`,
  ];
  return (
    <div className="flex items-center gap-3 px-5 py-2 border-b border-gray-200 bg-gray-50 text-xs text-gray-600">
      <span className="font-medium">Assessment:</span>
      {ASSESSMENT_COLORS.map((color, i) => (
        <span key={i} className="inline-flex items-center gap-1">
          <span className="inline-block w-3 h-3 rounded-sm border border-gray-300" style={{ backgroundColor: color }} />
          {labels[i]}
        </span>
      ))}
    </div>
  );
}

function fmtUSD(n: number | null | undefined) {
  if (n == null) return "—";
  return n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
}

function SelectionCard({ feature, onClose }: { feature: ParcelFeature; onClose: () => void }) {
  const p = feature.properties;
  return (
    <div className="absolute top-4 left-4 w-80 bg-white rounded-lg shadow-xl border border-gray-200 z-[1000]">
      <div className="px-4 py-3 border-b border-gray-200 flex items-start justify-between">
        <div>
          <h3 className="font-semibold text-gray-900 text-sm">
            Block {p.block}, Lot {p.lot}
            {p.qualifier ? <span className="text-gray-500 font-normal"> ({p.qualifier})</span> : null}
          </h3>
          {p.address && (
            <p className="text-xs text-gray-600 mt-0.5 flex items-center gap-1">
              <MapPinIcon className="w-3.5 h-3.5 text-gray-400" />
              {p.address}
            </p>
          )}
        </div>
        <button onClick={onClose} className="p-1 rounded hover:bg-gray-100 text-gray-500">
          <XMarkIcon className="w-4 h-4" />
        </button>
      </div>
      <dl className="px-4 py-3 text-sm space-y-1.5">
        <Row label="Class" value={p.property_class ?? "—"} />
        <Row label="Assessment" value={fmtUSD(p.total_assessment)} bold />
        <Row label="Tax" value={fmtUSD(p.tax_amount)} />
        <Row label="Year built" value={p.year_built ?? "—"} />
      </dl>
      <div className="px-4 py-2.5 border-t border-gray-100">
        <Link
          href={`/parcels?id=${feature.id}`}
          className="inline-flex items-center justify-center gap-1.5 w-full px-3 py-1.5 text-sm rounded-md text-white"
          style={{ backgroundColor: brandColor }}
        >
          Full details
          <ArrowTopRightOnSquareIcon className="w-3.5 h-3.5" />
        </Link>
      </div>
    </div>
  );
}

function Row({ label, value, bold }: { label: string; value: React.ReactNode; bold?: boolean }) {
  return (
    <div className="flex justify-between text-sm">
      <dt className="text-gray-500">{label}</dt>
      <dd className={`${bold ? "font-semibold text-gray-900" : "text-gray-700"}`}>{value}</dd>
    </div>
  );
}
