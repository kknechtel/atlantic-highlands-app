"use client";

import { useMemo } from "react";
import { MapContainer, TileLayer, GeoJSON } from "react-leaflet";
import type { Layer } from "leaflet";
import type { ParcelFeature } from "@/app/parcels/map/page";

interface Props {
  features: ParcelFeature[];
  bins: number[];
  colors: string[];
  onSelect: (feature: ParcelFeature) => void;
}

// Atlantic Highlands borough — rough center of the parcel set. Zoom 14 frames
// the whole town comfortably on a typical viewport without cutting off the
// peripheral parcels along the harbor or Memorial Pkwy.
const AH_CENTER: [number, number] = [40.4117, -74.0354];
const AH_ZOOM = 14;

/**
 * Color a parcel by its assessment relative to the precomputed quantile bins.
 * 5-bin chloropleth: parcels with no assessment or 0 get the bottom color.
 */
function colorFor(value: number | null, bins: number[], colors: string[]): string {
  if (!value || value <= 0) return colors[0];
  for (let i = 0; i < bins.length; i++) {
    if (value < bins[i]) return colors[i];
  }
  return colors[colors.length - 1];
}

export default function ParcelMap({ features, bins, colors, onSelect }: Props) {
  const fc = useMemo<GeoJSON.FeatureCollection>(
    () => ({ type: "FeatureCollection", features: features as any }),
    [features],
  );

  // Re-key the GeoJSON layer on every filter change so react-leaflet rebuilds
  // it (the layer is otherwise immutable per Leaflet's design).
  const layerKey = `${features.length}-${bins.join(",")}`;

  return (
    <MapContainer center={AH_CENTER} zoom={AH_ZOOM} className="w-full h-full" preferCanvas>
      {/* OpenStreetMap base tiles — free for non-commercial use within OSM's
          tile-usage policy. For production we'd switch to a CDN provider
          (Stadia, MapTiler) that has a free tier + better SLAs. */}
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <GeoJSON
        key={layerKey}
        data={fc}
        style={(feat) => {
          const f = feat as ParcelFeature;
          return {
            color: "#334155",
            weight: 0.4,
            fillColor: colorFor(f.properties.total_assessment, bins, colors),
            fillOpacity: 0.65,
          };
        }}
        onEachFeature={(feat, layer: Layer) => {
          const f = feat as ParcelFeature;
          layer.on({
            click: () => onSelect(f),
            mouseover: (e: any) => {
              e.target.setStyle({ weight: 2, color: "#0f172a" });
              e.target.bringToFront();
            },
            mouseout: (e: any) => {
              e.target.setStyle({ weight: 0.4, color: "#334155" });
            },
          });
        }}
      />
    </MapContainer>
  );
}
