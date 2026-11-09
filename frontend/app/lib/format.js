// Shared labels, colour scales and formatting helpers.

export const HORIZONS = [7, 14, 21, 30];
export const HORIZON_LABEL = { 7: "Week 1", 14: "Weeks 1–2", 21: "Weeks 1–3", 30: "Weeks 1–4" };

export const EVENTS = [
  { key: "onset", field: "prob_onset", label: "Onset", short: "Onset", palette: "green" },
  { key: "false_onset", field: "prob_false_onset", label: "False onset", short: "False onset", palette: "amber" },
  { key: "dry_spell", field: "prob_dry_spell_7d", label: "Dry spell (7+ days)", short: "Dry spell", palette: "red" },
  { key: "dry_spell_14d", field: "prob_dry_spell_14d", label: "Long break (14+ days)", short: "Long break", palette: "red" },
  { key: "heavy_rain", field: "prob_heavy_rain", label: "Heavy rain (65+ mm/day)", short: "Heavy rain", palette: "blue" },
  { key: "rainfall", field: "rainfall_median", label: "Expected rain (median, mm)", short: "Rain mm", palette: "rain", unit: "mm" },
];
export const EVENT_BY_KEY = Object.fromEntries(EVENTS.map((e) => [e.key, e]));

// Sequential light → dark scales (low value = light) for the light portal basemap.
export const PALETTES = {
  green: ["#f2f9d4", "#c2e699", "#78c679", "#31a354", "#006837"],
  amber: ["#fff7cc", "#fee391", "#fec44f", "#ec7014", "#993404"],
  red: ["#fee5d9", "#fcae91", "#fb6a4a", "#de2d26", "#a50f15"],
  blue: ["#e8f0fb", "#bdd7e7", "#6baed6", "#3182bd", "#08519c"],
  rain: ["#a6611a", "#dfc27d", "#c6dbef", "#4292c6", "#084594"],
};
// Map colour for blocks where onset is already established (distinct from every risk scale).
export const ONSET_ESTABLISHED_COLOR = "#3b2f8f";

export function rainMax(h) {
  return { 7: 60, 14: 110, 21: 160, 30: 220 }[h] || 100;
}

export const ACTION_LABEL = {
  SOW: "Sow now", WAIT: "Wait", SWITCH: "Switch crop", PROTECT: "Protect crop", IRRIGATE: "Irrigate",
  CONSERVE: "Conserve moisture", PREPARE: "Prepare for heavy rain", ALERT: "Very heavy rain alert",
  RESOW_ALERT: "Resowing may be needed", NORMAL: "Normal",
};
export const ACTION_COLOR = {
  SOW: "#10b981", WAIT: "#f59e0b", SWITCH: "#ef4444", PROTECT: "#3b82f6", IRRIGATE: "#06b6d4",
  CONSERVE: "#8b5cf6", PREPARE: "#6366f1", ALERT: "#dc2626", RESOW_ALERT: "#f97316", NORMAL: "#64748b",
};

export const CROPS = [
  { key: "cotton", en: "Cotton", te: "పత్తి", hi: "कपास", icon: "🌿" },
  { key: "soybean", en: "Soybean", te: "సోయాబీన్", hi: "सोयाबीन", icon: "🫘" },
  { key: "groundnut", en: "Groundnut", te: "వేరుశెనగ", hi: "मूंगफली", icon: "🥜" },
  { key: "paddy", en: "Paddy", te: "వరి", hi: "धान", icon: "🌾" },
];

export const ONSET_STATUS = {
  not_yet: { label: "Not yet", color: "#475569" },
  provisional: { label: "Provisional (watch for false onset)", color: "#b45309" },
  established: { label: "Established", color: "#047857" },
  false_onset: { label: "False onset — rains failed", color: "#b91c1c" },
};

export const REGIME = {
  pre_onset: "Pre-onset", active: "Active monsoon", break: "Break (dry phase)", transition: "Transition",
};

export const pct = (x) => (x === null || x === undefined || Number.isNaN(x) ? "–" : `${Math.round(x * 100)}%`);
export const mm = (x) => (x === null || x === undefined ? "–" : `${Math.round(x)} mm`);

export function fmtDate(s, opts = { day: "numeric", month: "short", year: "numeric" }) {
  if (!s) return "–";
  const d = new Date(`${s}T00:00:00`);
  return d.toLocaleDateString("en-IN", opts);
}

export function colorFor(value, palette, max = 1) {
  const stops = PALETTES[palette] || PALETTES.blue;
  if (value === null || value === undefined) return "#d6dce4";
  const t = Math.max(0, Math.min(1, value / max)) * (stops.length - 1);
  const i = Math.floor(t);
  return stops[Math.min(i + (t - i > 0.5 ? 1 : 0), stops.length - 1)];
}
