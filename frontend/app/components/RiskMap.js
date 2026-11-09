"use client";

import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { colorFor } from "../lib/format";

/**
 * RiskMap — block / panchayat choropleth of forecast probabilities.
 *
 * props
 *   districts, blocks, panchayats : GeoJSON FeatureCollections
 *   level      : "block" | "panchayat"
 *   values     : { [id]: number|null }   value per feature id for the active level
 *   palette    : palette key (lib/format PALETTES), max: value mapped to the top colour
 *   overrides  : { [id]: { color, label } } e.g. blocks where onset is already established
 *   labelFor   : (props, value) => string  hover text
 *   selectedId : id of the selected feature (active level)
 *   onSelect   : (props) => void
 */
const EMPTY = { type: "FeatureCollection", features: [] };

export default function RiskMap({
  districts, blocks, panchayats, level = "block", values = {}, palette = "red", max = 1,
  overrides = {}, labelFor, selectedId = null, onSelect,
}) {
  const container = useRef(null);
  const mapRef = useRef(null);
  const handlers = useRef({ onSelect, labelFor, level });
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    handlers.current = { onSelect, labelFor, level };
  }, [onSelect, labelFor, level]);

  useEffect(() => {
    if (mapRef.current || !container.current) return;
    // Risk layers are part of the initial style, so they render as soon as the style is parsed,
    // independent of basemap tiles (which may be slow or blocked on venue networks).
    const geo = { type: "geojson", data: EMPTY };
    const map = new maplibregl.Map({
      container: container.current,
      style: {
        version: 8,
        glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
        sources: {
          osm: {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            maxzoom: 19,
            attribution: "&copy; OpenStreetMap contributors",
          },
          districts: geo, blocks: geo, panchayats: geo, selected: geo,
        },
        layers: [
          { id: "bg", type: "background", paint: { "background-color": "#e8edf3" } },
          // keyless OSM tiles, softly desaturated to sit under the risk colours
          { id: "osm", type: "raster", source: "osm",
            paint: { "raster-saturation": -0.75, "raster-contrast": -0.05, "raster-opacity": 0.85 } },
          { id: "panch-fill", type: "fill", source: "panchayats",
            paint: { "fill-color": ["coalesce", ["get", "color"], "rgba(0,0,0,0)"], "fill-opacity": 0.78 }, layout: { visibility: "none" } },
          { id: "panch-line", type: "line", source: "panchayats", paint: { "line-color": "#ffffff", "line-width": 0.7 },
            layout: { visibility: "none" } },
          { id: "block-fill", type: "fill", source: "blocks",
            paint: { "fill-color": ["coalesce", ["get", "color"], "rgba(0,0,0,0)"], "fill-opacity": 0.8 } },
          { id: "block-line", type: "line", source: "blocks", paint: { "line-color": "#ffffff", "line-width": 1.2 } },
          { id: "district-line", type: "line", source: "districts",
            paint: { "line-color": "#12355b", "line-width": 1.6, "line-dasharray": [3, 2] } },
          { id: "selected-line", type: "line", source: "selected", paint: { "line-color": "#0a2540", "line-width": 3.2 } },
          { id: "block-label", type: "symbol", source: "blocks", minzoom: 7.2,
            layout: { "text-field": ["get", "name"], "text-size": 11, "text-font": ["Open Sans Regular"] },
            paint: { "text-color": "#0a2540", "text-halo-color": "#ffffff", "text-halo-width": 1.6 } },
          { id: "district-label", type: "symbol", source: "districts", maxzoom: 7.4,
            layout: { "text-field": ["get", "name"], "text-size": 13, "text-font": ["Open Sans Semibold"], "text-allow-overlap": true },
            paint: { "text-color": "#12355b", "text-halo-color": "#ffffff", "text-halo-width": 2 } },
        ],
      },
      center: [78.5, 17.0],
      zoom: 6.6,
      minZoom: 5,
      maxZoom: 13,
      attributionControl: { compact: true },
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 8 });

    for (const layer of ["block-fill", "panch-fill"]) {
      const active = () => (layer === "block-fill") === (handlers.current.level === "block");
      map.on("click", layer, (e) => {
        const f = e.features?.[0];
        if (f && active()) handlers.current.onSelect?.(f.properties);
      });
      map.on("mousemove", layer, (e) => {
        const f = e.features?.[0];
        if (!f || !active()) return;
        map.getCanvas().style.cursor = "pointer";
        popup.setLngLat(e.lngLat).setHTML(f.properties.label || f.properties.name).addTo(map);
      });
      map.on("mouseleave", layer, () => {
        map.getCanvas().style.cursor = "";
        popup.remove();
      });
    }
    const ready = () => setLoaded(true);
    if (map.isStyleLoaded()) ready();
    else map.once("styledata", ready);

    mapRef.current = map;
    if (process.env.NODE_ENV !== "production") window.__varshaMap = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Data / styling updates
  useEffect(() => {
    const map = mapRef.current;
    if (!loaded || !map) return;
    if (districts) map.getSource("districts").setData(districts);
    const paint = (fc) => ({
      ...fc,
      features: (fc?.features || []).map((f) => {
        const id = f.properties.id;
        const v = values[id];
        const ov = overrides[id];
        return {
          ...f,
          properties: {
            ...f.properties,
            value: v ?? null,
            color: ov?.color || colorFor(v, palette, max),
            label: labelFor ? labelFor(f.properties, v, ov) : f.properties.name,
          },
        };
      }),
    });
    const isBlock = level === "block";
    if (blocks) map.getSource("blocks").setData(isBlock ? paint(blocks) : { ...blocks, features: blocks.features.map((f) => ({ ...f, properties: { ...f.properties, color: "rgba(0,0,0,0)", label: f.properties.name } })) });
    if (panchayats) map.getSource("panchayats").setData(isBlock ? EMPTY : paint(panchayats));
    map.setLayoutProperty("panch-fill", "visibility", isBlock ? "none" : "visible");
    map.setLayoutProperty("panch-line", "visibility", isBlock ? "none" : "visible");
    map.setPaintProperty("block-fill", "fill-opacity", isBlock ? 0.8 : 0);
    map.setPaintProperty("block-line", "line-color", isBlock ? "#ffffff" : "#12355b");
    map.setPaintProperty("block-line", "line-width", isBlock ? 1.2 : 1.4);
  }, [loaded, districts, blocks, panchayats, level, values, palette, max, overrides, labelFor]);

  // Selection outline
  useEffect(() => {
    const map = mapRef.current;
    if (!loaded || !map) return;
    const fc = level === "block" ? blocks : panchayats;
    const feat = fc?.features?.find((f) => f.properties.id === selectedId);
    map.getSource("selected").setData(feat ? { type: "FeatureCollection", features: [feat] } : EMPTY);
  }, [loaded, selectedId, level, blocks, panchayats]);

  return <div ref={container} style={{ position: "absolute", inset: 0, background: "var(--color-bg-primary)" }} />;
}
