"use client";

import { useState, useEffect } from "react";
import dynamic from "next/dynamic";

// Dynamic import for MapLibre to avoid SSR issues
const RiskMap = dynamic(() => import("./components/RiskMap"), { ssr: false });

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Dashboard() {
  const [districts, setDistricts] = useState(null);
  const [blocks, setBlocks] = useState(null);
  const [selectedBlock, setSelectedBlock] = useState(null);
  const [activeTab, setActiveTab] = useState("onset");
  const [horizon, setHorizon] = useState(7);

  useEffect(() => {
    // Load boundary GeoJSON from public directory (works without backend)
    fetch("/boundaries/districts.geojson")
      .then((r) => r.json())
      .then(setDistricts)
      .catch(() => console.log("Districts GeoJSON not loaded"));

    fetch("/boundaries/blocks.geojson")
      .then((r) => r.json())
      .then(setBlocks)
      .catch(() => console.log("Blocks GeoJSON not loaded"));
  }, []);

  const riskTabs = [
    { key: "onset", label: "🌱 Onset", color: "#10b981" },
    { key: "false_onset", label: "⚠️ False Onset", color: "#f59e0b" },
    { key: "dry_spell", label: "☀️ Dry Spell", color: "#ef4444" },
    { key: "heavy_rain", label: "🌧️ Heavy Rain", color: "#3b82f6" },
  ];

  const horizonOptions = [
    { days: 7, label: "Week 1" },
    { days: 14, label: "Week 2" },
    { days: 21, label: "Week 3" },
    { days: 30, label: "Week 4" },
  ];

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      {/* Header */}
      <header
        className="glass"
        style={{
          padding: "12px 24px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderBottom: "1px solid var(--border-color)",
          position: "sticky",
          top: 0,
          zIndex: 100,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontSize: "1.5rem" }}>🌧️</span>
          <div>
            <h1
              style={{
                margin: 0,
                fontSize: "1.25rem",
                fontWeight: 700,
                background: "linear-gradient(135deg, #3b82f6, #06b6d4)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
              }}
            >
              Varsha
            </h1>
            <p
              style={{
                margin: 0,
                fontSize: "0.7rem",
                color: "var(--color-text-muted)",
                letterSpacing: "0.1em",
                textTransform: "uppercase",
              }}
            >
              Monsoon Intelligence System
            </p>
          </div>
        </div>

        <nav style={{ display: "flex", gap: 8 }}>
          {[
            { href: "/", label: "Dashboard", active: true },
            { href: "/officer", label: "Officer Console" },
            { href: "/replay", label: "Replay" },
          ].map((link) => (
            <a
              key={link.label}
              href={link.href}
              style={{
                padding: "6px 14px",
                borderRadius: "var(--radius-sm)",
                fontSize: "0.8rem",
                fontWeight: 500,
                color: link.active
                  ? "var(--color-text-primary)"
                  : "var(--color-text-secondary)",
                background: link.active
                  ? "rgba(59, 130, 246, 0.15)"
                  : "transparent",
                border: link.active
                  ? "1px solid rgba(59, 130, 246, 0.3)"
                  : "1px solid transparent",
                textDecoration: "none",
                transition: "all 0.2s",
              }}
            >
              {link.label}
            </a>
          ))}
        </nav>

        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span
            style={{
              fontSize: "0.75rem",
              color: "var(--color-text-muted)",
            }}
          >
            Telangana Pilot
          </span>
          <div className="synthetic-warning">⚠️ SYNTHETIC DATA</div>
        </div>
      </header>

      {/* Main Content */}
      <main
        style={{
          flex: 1,
          display: "grid",
          gridTemplateColumns: "1fr 380px",
          gap: 0,
          height: "calc(100vh - 64px)",
        }}
      >
        {/* Map Panel */}
        <div style={{ position: "relative" }}>
          {/* Risk Type Tabs */}
          <div
            className="glass"
            style={{
              position: "absolute",
              top: 16,
              left: 16,
              zIndex: 10,
              display: "flex",
              gap: 4,
              padding: 4,
              borderRadius: "var(--radius-md)",
            }}
          >
            {riskTabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                style={{
                  padding: "8px 14px",
                  borderRadius: "var(--radius-sm)",
                  border: "none",
                  cursor: "pointer",
                  fontSize: "0.8rem",
                  fontWeight: 600,
                  color:
                    activeTab === tab.key
                      ? "#fff"
                      : "var(--color-text-secondary)",
                  background:
                    activeTab === tab.key
                      ? `${tab.color}33`
                      : "transparent",
                  borderBottom:
                    activeTab === tab.key
                      ? `2px solid ${tab.color}`
                      : "2px solid transparent",
                  transition: "all 0.2s",
                }}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Horizon Selector */}
          <div
            className="glass"
            style={{
              position: "absolute",
              top: 16,
              right: 16,
              zIndex: 10,
              display: "flex",
              gap: 4,
              padding: 4,
              borderRadius: "var(--radius-md)",
            }}
          >
            {horizonOptions.map((opt) => (
              <button
                key={opt.days}
                onClick={() => setHorizon(opt.days)}
                style={{
                  padding: "8px 12px",
                  borderRadius: "var(--radius-sm)",
                  border: "none",
                  cursor: "pointer",
                  fontSize: "0.75rem",
                  fontWeight: 600,
                  color:
                    horizon === opt.days
                      ? "var(--color-accent-cyan)"
                      : "var(--color-text-muted)",
                  background:
                    horizon === opt.days
                      ? "rgba(6, 182, 212, 0.15)"
                      : "transparent",
                  transition: "all 0.2s",
                }}
              >
                {opt.label}
              </button>
            ))}
          </div>

          {/* Map */}
          <RiskMap
            districts={districts}
            blocks={blocks}
            activeTab={activeTab}
            onBlockSelect={setSelectedBlock}
          />
        </div>

        {/* Side Panel */}
        <aside
          className="glass"
          style={{
            borderLeft: "1px solid var(--border-color)",
            overflowY: "auto",
            padding: "20px",
          }}
        >
          {selectedBlock ? (
            <BlockDetail block={selectedBlock} />
          ) : (
            <PilotOverview blocks={blocks} />
          )}
        </aside>
      </main>
    </div>
  );
}

function PilotOverview({ blocks }) {
  const blockCount = blocks?.features?.length || 0;

  return (
    <div className="animate-fade-in">
      <h2
        style={{
          fontSize: "1.1rem",
          fontWeight: 700,
          margin: "0 0 4px 0",
        }}
      >
        Telangana Pilot Region
      </h2>
      <p
        style={{
          fontSize: "0.8rem",
          color: "var(--color-text-secondary)",
          margin: "0 0 20px 0",
        }}
      >
        Mahbubnagar · Nalgonda · Medak
      </p>

      {/* Stats */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 12,
          marginBottom: 20,
        }}
      >
        {[
          { label: "Districts", value: "3", icon: "🏛️" },
          { label: "Blocks", value: String(blockCount), icon: "📍" },
          { label: "Panchayats", value: "125", icon: "🏘️" },
          { label: "Crops", value: "4", icon: "🌾" },
        ].map((stat) => (
          <div
            key={stat.label}
            className="card"
            style={{ padding: "14px", textAlign: "center" }}
          >
            <div style={{ fontSize: "1.5rem", marginBottom: 4 }}>
              {stat.icon}
            </div>
            <div
              style={{
                fontSize: "1.5rem",
                fontWeight: 800,
                color: "var(--color-accent-cyan)",
              }}
            >
              {stat.value}
            </div>
            <div
              style={{
                fontSize: "0.7rem",
                color: "var(--color-text-muted)",
                textTransform: "uppercase",
                letterSpacing: "0.05em",
              }}
            >
              {stat.label}
            </div>
          </div>
        ))}
      </div>

      {/* Crops */}
      <h3
        style={{
          fontSize: "0.85rem",
          fontWeight: 600,
          color: "var(--color-text-secondary)",
          margin: "0 0 12px 0",
          textTransform: "uppercase",
          letterSpacing: "0.1em",
        }}
      >
        Pilot Crops
      </h3>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {[
          { name: "Cotton (పత్తి)", icon: "🌿", stage: "Sowing window open" },
          { name: "Soybean (సోయాబీన్)", icon: "🫘", stage: "Pre-sowing" },
          { name: "Groundnut (వేరుశెనగ)", icon: "🥜", stage: "Pre-sowing" },
          { name: "Paddy (వరి)", icon: "🌾", stage: "Nursery preparation" },
        ].map((crop) => (
          <div
            key={crop.name}
            className="card"
            style={{
              padding: "12px 16px",
              display: "flex",
              alignItems: "center",
              gap: 12,
            }}
          >
            <span style={{ fontSize: "1.3rem" }}>{crop.icon}</span>
            <div>
              <div style={{ fontSize: "0.85rem", fontWeight: 600 }}>
                {crop.name}
              </div>
              <div
                style={{
                  fontSize: "0.7rem",
                  color: "var(--color-text-muted)",
                }}
              >
                {crop.stage}
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="synthetic-warning" style={{ marginTop: 20 }}>
        ⚠️ This prototype uses SYNTHETIC boundaries and placeholder data.
        Real data pipeline is under development.
      </div>

      <p
        style={{
          fontSize: "0.75rem",
          color: "var(--color-text-muted)",
          marginTop: 16,
          textAlign: "center",
        }}
      >
        Click a block on the map to see details →
      </p>
    </div>
  );
}

function BlockDetail({ block }) {
  return (
    <div className="animate-fade-in">
      <button
        onClick={() => window.location.reload()}
        style={{
          background: "none",
          border: "none",
          color: "var(--color-accent-blue)",
          cursor: "pointer",
          fontSize: "0.8rem",
          padding: 0,
          marginBottom: 12,
        }}
      >
        ← Back to overview
      </button>

      <h2 style={{ fontSize: "1.1rem", fontWeight: 700, margin: "0 0 4px 0" }}>
        {block.name}
      </h2>
      <p
        style={{
          fontSize: "0.8rem",
          color: "var(--color-text-secondary)",
          margin: "0 0 20px 0",
        }}
      >
        {block.district} · Block / Mandal
      </p>

      {/* Placeholder for forecast data */}
      <div className="card" style={{ padding: 20, textAlign: "center" }}>
        <p style={{ color: "var(--color-text-muted)", fontSize: "0.85rem" }}>
          📊 Forecast data will appear here after the pipeline runs.
        </p>
        <p
          style={{
            color: "var(--color-text-muted)",
            fontSize: "0.75rem",
            marginTop: 8,
          }}
        >
          Milestone 2: Data fetchers → Milestone 4: Models
        </p>
      </div>
    </div>
  );
}
