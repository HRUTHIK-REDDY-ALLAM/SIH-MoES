"use client";

import {
  Area, Bar, CartesianGrid, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Scatter, Tooltip,
  XAxis, YAxis,
} from "recharts";
import { HORIZON_LABEL, fmtDate } from "../lib/format";

const AXIS = { stroke: "#6b7a90", fontSize: 11 };
const GRID = "rgba(148,163,184,0.12)";
const TT = {
  contentStyle: { background: "#151d2e", border: "1px solid rgba(148,163,184,.3)", borderRadius: 8, fontSize: 12 },
  labelStyle: { color: "#a3b1c6" },
};

/** Rainfall outlook: q10–q90 band, q25–q75 band and median per horizon. */
export function RainFan({ horizons }) {
  const data = horizons.map((h) => ({
    name: HORIZON_LABEL[h.horizon_days] || `${h.horizon_days}d`,
    outer: [h.rainfall_q10, h.rainfall_q90],
    inner: [h.rainfall_q25, h.rainfall_q75],
    median: h.rainfall_median,
  }));
  return (
    <ResponsiveContainer width="100%" height={190}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="name" tick={AXIS} />
        <YAxis tick={AXIS} unit=" mm" width={58} />
        <Tooltip {...TT} formatter={(v) => (Array.isArray(v) ? `${Math.round(v[0])}–${Math.round(v[1])} mm` : `${Math.round(v)} mm`)} />
        <Area dataKey="outer" name="10–90% range" fill="#2563eb" fillOpacity={0.18} stroke="none" />
        <Area dataKey="inner" name="25–75% range" fill="#2563eb" fillOpacity={0.35} stroke="none" />
        <Line dataKey="median" name="Median" stroke="#67e8f9" strokeWidth={2} dot={{ r: 3 }} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

/** Season so far: observed daily rain (bars) and the 7-day forecast probability issued each day. */
export function SeasonChart({ series, observations, field = "prob_dry_spell_7d", climField = "clim_dry_spell_7d",
  label = "Dry-spell chance (next 7 days)", height = 220, markDate = null }) {
  const obsBy = Object.fromEntries((observations || []).map((o) => [o.date, o.rain]));
  const data = (series || []).map((p) => ({
    date: p.date, rain: obsBy[p.date] ?? null, prob: p[field], clim: climField ? p[climField] : null,
  }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 8, right: 0, bottom: 0, left: -18 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="date" tick={AXIS} tickFormatter={(d) => fmtDate(d, { day: "numeric", month: "short" })} minTickGap={24} />
        <YAxis yAxisId="p" tick={AXIS} domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} width={46} />
        <YAxis yAxisId="r" orientation="right" tick={AXIS} width={40} unit="" />
        <Tooltip {...TT} labelFormatter={(d) => fmtDate(d)}
          formatter={(v, n) => (n === "Observed rain" ? `${v ?? 0} mm` : `${Math.round((v || 0) * 100)}%`)} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Bar yAxisId="r" dataKey="rain" name="Observed rain" fill="#38bdf8" opacity={0.55} />
        <Line yAxisId="p" dataKey="prob" name={label} stroke="#f87171" dot={false} strokeWidth={2} />
        {climField && <Line yAxisId="p" dataKey="clim" name="Climatology" stroke="#cbd5e1" dot={false} strokeDasharray="4 3" />}
        {markDate && <ReferenceLine yAxisId="p" x={markDate} stroke="#fbbf24" />}
      </ComposedChart>
    </ResponsiveContainer>
  );
}

/** Replay chart: observed rain + forecast probability for one block over the season. */
export function ReplayChart({ dates, rain, prob, label, markDate, events = [] }) {
  const data = dates.map((d, i) => ({ date: d, rain: rain[i], prob: prob[i] }));
  return (
    <ResponsiveContainer width="100%" height={230}>
      <ComposedChart data={data} margin={{ top: 8, right: 0, bottom: 0, left: -18 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="date" tick={AXIS} tickFormatter={(d) => fmtDate(d, { day: "numeric", month: "short" })} minTickGap={28} />
        <YAxis yAxisId="p" tick={AXIS} domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} width={46} />
        <YAxis yAxisId="r" orientation="right" tick={AXIS} width={40} />
        <Tooltip {...TT} labelFormatter={(d) => fmtDate(d)}
          formatter={(v, n) => (n === "Observed rain" ? `${v ?? 0} mm` : `${Math.round((v || 0) * 100)}%`)} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Bar yAxisId="r" dataKey="rain" name="Observed rain" fill="#38bdf8" opacity={0.6} />
        <Line yAxisId="p" dataKey="prob" name={label} stroke="#f87171" dot={false} strokeWidth={2} />
        {events.map((e) => (
          <ReferenceLine key={e.date + e.type} yAxisId="p" x={e.date} stroke="rgba(203,213,225,.35)" strokeDasharray="2 3" />
        ))}
        {markDate && <ReferenceLine yAxisId="p" x={markDate} stroke="#fbbf24" strokeWidth={2} />}
      </ComposedChart>
    </ResponsiveContainer>
  );
}

/** Reliability diagram: forecast probability vs observed frequency. */
export function ReliabilityChart({ bins }) {
  const data = (bins || []).map((b) => ({ x: b.forecast, y: b.observed, n: b.count }));
  return (
    <ResponsiveContainer width="100%" height={240}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 8, left: -12 }}>
        <CartesianGrid stroke={GRID} />
        <XAxis type="number" dataKey="x" domain={[0, 1]} tick={AXIS} tickFormatter={(v) => `${Math.round(v * 100)}%`}
          label={{ value: "Forecast probability", position: "insideBottom", offset: -4, fill: "#6b7a90", fontSize: 11 }} />
        <YAxis type="number" domain={[0, 1]} tick={AXIS} tickFormatter={(v) => `${Math.round(v * 100)}%`} width={50} />
        <Tooltip {...TT} formatter={(v, n) => (n === "n" ? v : `${Math.round(v * 100)}%`)} />
        <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]} stroke="#64748b" strokeDasharray="4 4" />
        <Line dataKey="y" name="Observed frequency" stroke="#34d399" strokeWidth={2} dot={{ r: 4 }} />
        <Scatter dataKey="y" fill="#34d399" />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
