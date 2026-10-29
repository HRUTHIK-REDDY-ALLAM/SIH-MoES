"use client";

import { useRef, useEffect, useState, useCallback } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

/**
 * RiskMap — MapLibre GL component showing pilot region blocks
 * with color-coded risk overlays.
 *
 * For M1 this shows the SYNTHETIC block boundaries.
 * In later milestones, fill colors will be driven by forecast probabilities.
 */
export default function RiskMap({ districts, blocks, activeTab, onBlockSelect }) {
  const mapContainer = useRef(null);
  const mapRef = useRef(null);
  const [mapLoaded, setMapLoaded] = useState(false);

  // Risk color scales per tab
  const riskColors = {
    onset: ["#064e3b", "#059669", "#10b981", "#34d399", "#6ee7b7"],
    false_onset: ["#78350f", "#d97706", "#f59e0b", "#fbbf24", "#fde68a"],
    dry_spell: ["#7f1d1d", "#dc2626", "#ef4444", "#f87171", "#fca5a5"],
    heavy_rain: ["#1e3a5f", "#1d4ed8", "#3b82f6", "#60a5fa", "#93c5fd"],
  };

  // Initialize map
  useEffect(() => {
    if (mapRef.current || !mapContainer.current) return;

    const map = new maplibregl.Map({
      container: mapContainer.current,
      style: {
        version: 8,
        glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
        sources: {
          "carto-dark": {
            type: "raster",
            tiles: [
              "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png",
              "https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png",
              "https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png",
            ],
            tileSize: 256,
            attribution: "&copy; CartoDB &copy; OpenStreetMap contributors",
          },
        },
        layers: [
          {
            id: "carto-dark-layer",
            type: "raster",
            source: "carto-dark",
            minzoom: 0,
            maxzoom: 19,
          },
        ],
      },
      center: [78.5, 17.0], // Center of Telangana pilot region
      zoom: 7.5,
      minZoom: 6,
      maxZoom: 14,
    });

    map.addControl(new maplibregl.NavigationControl(), "bottom-right");
    map.addControl(
      new maplibregl.ScaleControl({ maxWidth: 150, unit: "metric" }),
      "bottom-left"
    );

    map.on("load", () => {
      setMapLoaded(true);
    });

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Add district boundaries
  useEffect(() => {
    if (!mapLoaded || !mapRef.current || !districts) return;
    const map = mapRef.current;

    if (map.getSource("districts")) return;

    map.addSource("districts", {
      type: "geojson",
      data: districts,
    });

    map.addLayer({
      id: "district-borders",
      type: "line",
      source: "districts",
      paint: {
        "line-color": "#475569",
        "line-width": 2,
        "line-dasharray": [3, 2],
      },
    });

    map.addLayer({
      id: "district-labels",
      type: "symbol",
      source: "districts",
      layout: {
        "text-field": ["get", "name"],
        "text-size": 14,
        "text-font": ["Open Sans Bold"],
        "text-anchor": "center",
        "text-allow-overlap": true,
      },
      paint: {
        "text-color": "#94a3b8",
        "text-halo-color": "#0a0f1e",
        "text-halo-width": 2,
      },
    });
  }, [mapLoaded, districts]);

  // Add block boundaries with risk coloring
  useEffect(() => {
    if (!mapLoaded || !mapRef.current || !blocks) return;
    const map = mapRef.current;

    // Remove existing block layers
    if (map.getLayer("block-fills")) map.removeLayer("block-fills");
    if (map.getLayer("block-borders")) map.removeLayer("block-borders");
    if (map.getLayer("block-labels")) map.removeLayer("block-labels");
    if (map.getSource("blocks")) map.removeSource("blocks");

    // Assign random risk values for demo (will be replaced with real data)
    const dataWithRisk = {
      ...blocks,
      features: blocks.features.map((f, i) => ({
        ...f,
        properties: {
          ...f.properties,
          risk_value: Math.random(), // SYNTHETIC — placeholder
        },
      })),
    };

    map.addSource("blocks", {
      type: "geojson",
      data: dataWithRisk,
    });

    const colors = riskColors[activeTab] || riskColors.onset;

    map.addLayer(
      {
        id: "block-fills",
        type: "fill",
        source: "blocks",
        paint: {
          "fill-color": [
            "interpolate",
            ["linear"],
            ["get", "risk_value"],
            0, colors[0],
            0.25, colors[1],
            0.5, colors[2],
            0.75, colors[3],
            1, colors[4],
          ],
          "fill-opacity": 0.6,
        },
      },
      "district-borders"
    );

    map.addLayer({
      id: "block-borders",
      type: "line",
      source: "blocks",
      paint: {
        "line-color": "#334155",
        "line-width": 1,
      },
    });

    map.addLayer({
      id: "block-labels",
      type: "symbol",
      source: "blocks",
      layout: {
        "text-field": ["get", "name"],
        "text-size": 10,
        "text-font": ["Open Sans Regular"],
        "text-anchor": "center",
      },
      paint: {
        "text-color": "#e2e8f0",
        "text-halo-color": "#0f172a",
        "text-halo-width": 1,
      },
      minzoom: 8,
    });

    // Click handler
    map.on("click", "block-fills", (e) => {
      if (e.features && e.features.length > 0) {
        const feature = e.features[0];
        onBlockSelect?.({
          name: feature.properties.name,
          district: feature.properties.district,
          id: feature.properties.id,
        });
      }
    });

    // Hover effect
    map.on("mouseenter", "block-fills", () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", "block-fills", () => {
      map.getCanvas().style.cursor = "";
    });
  }, [mapLoaded, blocks, activeTab]);

  return (
    <div
      ref={mapContainer}
      style={{
        width: "100%",
        height: "100%",
        background: "var(--color-bg-primary)",
      }}
    />
  );
}
