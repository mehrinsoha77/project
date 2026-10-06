"use client";

import { useEffect } from "react";
import { CircleMarker, ImageOverlay, MapContainer, Polyline, TileLayer, Tooltip, useMap } from "react-leaflet";
import type { LatLngBoundsExpression } from "leaflet";
import type { Reach } from "@/lib/api";
import type { LatLon } from "@/lib/banks";

export type MapLine = {
  id: string;
  positions: LatLon[];
  color: string;
  weight: number;
  opacity?: number;
  dash?: string;
  tooltip?: string;
  interactive?: boolean;
};

export type MapMarker = {
  id: string;
  at: LatLon;
  color: string;
  radius: number;
  fillOpacity?: number;
  stroke?: string;
  label?: string;
  tooltip?: string;
};

type Props = {
  reach: Reach;
  image?: { url: string; opacity: number } | null;
  lines?: MapLine[];
  markers?: MapMarker[];
  onSelect?: (id: string) => void;
  street?: boolean;
  className?: string;
  focus?: LatLon | null;
};

function Fit({ reach }: { reach: Reach }) {
  const map = useMap();
  useEffect(() => {
    const [w, s, e, n] = reach.bbox;
    map.fitBounds([
      [s, w],
      [n, e],
    ]);
  }, [map, reach]);
  return null;
}

function Focus({ at }: { at: LatLon | null | undefined }) {
  const map = useMap();
  useEffect(() => {
    if (at) map.flyTo(at, Math.max(map.getZoom(), 13), { duration: 0.6 });
  }, [map, at]);
  return null;
}

export default function RiverMap({ reach, image, lines = [], markers = [], onSelect, street = false, className, focus }: Props) {
  const b = reach.image_bounds;
  const bounds: LatLngBoundsExpression | null = b
    ? [
        [b[0], b[1]],
        [b[2], b[3]],
      ]
    : null;
  return (
    <MapContainer
      className={className}
      center={[24.47, 89.77]}
      zoom={10}
      minZoom={9}
      maxZoom={16}
      preferCanvas
      zoomSnap={0.25}
      attributionControl
      style={{ height: "100%", width: "100%" }}
    >
      <Fit reach={reach} />
      <Focus at={focus} />
      {street && (
        <TileLayer
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution="&copy; OpenStreetMap contributors"
          opacity={0.9}
        />
      )}
      {image && bounds && (
        <ImageOverlay
          url={image.url}
          bounds={bounds}
          opacity={image.opacity}
          attribution="Contains modified Copernicus Sentinel-1 data"
        />
      )}
      {lines.map((l) => (
        <Polyline
          key={l.id}
          positions={l.positions}
          pathOptions={{ color: l.color, weight: l.weight, opacity: l.opacity ?? 1, dashArray: l.dash, lineCap: "round", lineJoin: "round" }}
          interactive={l.interactive ?? Boolean(onSelect)}
          eventHandlers={onSelect && (l.interactive ?? true) ? { click: () => onSelect(l.id.split("|")[0]) } : undefined}
        >
          {l.tooltip && (
            <Tooltip sticky className="seg-tip">
              {l.tooltip}
            </Tooltip>
          )}
        </Polyline>
      ))}
      {markers.map((m) => (
        <CircleMarker
          key={m.id}
          center={m.at}
          radius={m.radius}
          pathOptions={{ color: m.stroke ?? "#ffffff", weight: 2, fillColor: m.color, fillOpacity: m.fillOpacity ?? 1 }}
          eventHandlers={onSelect ? { click: () => onSelect(m.id.split("|")[0]) } : undefined}
        >
          {m.label && (
            <Tooltip permanent direction="right" offset={[6, 0]} className="rank-label">
              {m.label}
            </Tooltip>
          )}
          {m.tooltip && !m.label && (
            <Tooltip className="seg-tip" direction="top">
              {m.tooltip}
            </Tooltip>
          )}
        </CircleMarker>
      ))}
    </MapContainer>
  );
}
