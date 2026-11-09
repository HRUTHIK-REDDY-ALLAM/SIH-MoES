"use client";

import { useEffect, useState } from "react";
import Header from "../components/Header";
import { ReliabilityChart } from "../components/Charts";
import { SourceBadge } from "../components/Panels";
import { getLatest, getSkill } from "../lib/api";

const EVENTS = [
  ["onset", "Onset"], ["false_onset", "False onset"], ["dry_spell_7d", "Dry spell 7+ d"],
  ["dry_spell_14d", "Dry spell 14+ d"], ["heavy_rain", "Heavy rain"], ["very_heavy_rain", "Very heavy rain"],
];
const H = ["7", "14", "21", "30"];

function cellColor(bss) {
  if (bss == null || Number.isNaN(bss)) return "transparent";
  if (bss >= 0.15) return "rgba(16,185,129,.35)";
  if (bss >= 0.05) return "rgba(16,185,129,.18)";
  if (bss >= -0.02) return "rgba(148,163,184,.12)";
  return "rgba(244,63,94,.22)";
}

function SkillTable({ table, title, note }) {
  if (!table?.by_event) return null;
  return (
    <div className="card">
      <strong className="small">{title}</strong>
      <div className="tbl-wrap" style={{ marginTop: 8 }}>
        <table className="tbl">
          <thead>
            <tr><th>Event</th>{H.map((h) => <th key={h} className="num">{h} days</th>)}</tr>
          </thead>
          <tbody>
            {EVENTS.map(([k, label]) => (
              <tr key={k}>
                <td>{label}</td>
                {H.map((h) => {
                  const m = table.by_event[k]?.[h];
                  return (
                    <td key={h} className="num" style={{ background: cellColor(m?.bss) }} title={m ? `base rate ${Math.round(m.base_rate * 100)}%` : ""}>
                      {m ? <>{m.bss >= 0 ? "+" : ""}{m.bss.toFixed(2)} <span className="tiny muted">/ {m.auc?.toFixed(2)}</span></> : "–"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="tiny muted" style={{ margin: "8px 0 0" }}>{note}</p>
    </div>
  );
}

export default function SkillPage() {
  const [rep, setRep] = useState(null);
  const [source, setSource] = useState(null);
  const [blocks, setBlocks] = useState([]);
  const [ev, setEv] = useState("dry_spell_7d");
  const [h, setH] = useState("7");
  const [err, setErr] = useState(null);

  useEffect(() => {
    getSkill().then(({ data, source }) => { setRep(data); setSource(source); }).catch((e) => setErr(e.message));
    getLatest().then(({ data }) => setBlocks(data.blocks)).catch(() => {});
  }, []);

  const hind = rep?.skill?.hindcast;
  const hold = rep?.skill?.holdout_2023;
  const rel = hind?.by_event?.[ev]?.[h]?.reliability;
  const rain = hind?.rainfall;

  return (
    <>
      <Header right={<SourceBadge source={source} synthetic />} />
      <div className="page">
        <h2 className="panel-title">Forecast verification</h2>
        <p className="small secondary" style={{ maxWidth: 820 }}>
          Every number below comes from forecasts made without seeing the season being scored. Hindcasts use
          leave-years-out cross-validation over {rep?.train_years?.[0]}–{rep?.train_years?.at(-1)} ({rep?.n_training_rows?.toLocaleString()} block-date-lead rows);
          the reference forecast is each block&apos;s own day-of-year climatology refitted without the test years.
          BSS &gt; 0 means better than climatology; AUC measures how well risky days are ranked (0.5 = no skill).
        </p>
        {err && <div className="notice error">{err}</div>}
        {rep && !hind && <div className="notice">No skill report yet — run <code>python -m models.train</code>.</div>}
        {hind && (
          <div className="stack" style={{ marginTop: 14 }}>
            <SkillTable table={hind} title="Hindcast: Brier Skill Score / ROC AUC by lead time"
              note="Green = skilful. Probabilities are isotonic-calibrated with cross-fitting, so calibration is also judged out of sample." />
            <SkillTable table={hold} title="Held-out 2023 season (never used in training)"
              note="One season only: scores are noisy. The scripted 2023 season contains an unusually long August break." />

            <div className="grid-2">
              <div className="card">
                <div className="row between">
                  <strong className="small">Reliability diagram</strong>
                  <div className="row">
                    <select value={ev} onChange={(e) => setEv(e.target.value)}>
                      {EVENTS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                    </select>
                    <select value={h} onChange={(e) => setH(e.target.value)}>
                      {H.map((x) => <option key={x} value={x}>{x} days</option>)}
                    </select>
                  </div>
                </div>
                <ReliabilityChart bins={rel} />
                <p className="tiny muted" style={{ margin: 0 }}>Points on the diagonal = when Varsha says 40%, the event happens about 40% of the time.</p>
              </div>
              <div className="card">
                <strong className="small">Rainfall amount (quantile forecasts)</strong>
                <div className="tbl-wrap" style={{ marginTop: 8 }}>
                  <table className="tbl">
                    <thead><tr><th>Window</th><th className="num">Pinball (model)</th><th className="num">Pinball (clim.)</th><th className="num">10–90% coverage</th><th className="num">Corr.</th></tr></thead>
                    <tbody>
                      {Object.entries(rain || {}).map(([k, m]) => (
                        <tr key={k}><td>{k} days</td><td className="num">{m.pinball_median}</td><td className="num">{m.pinball_median_clim}</td>
                          <td className="num">{Math.round(m.coverage_q10_q90 * 100)}%</td><td className="num">{m.corr_median}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="tiny muted">Lower pinball loss than climatology = sharper, still honest rainfall ranges. Ideal 10–90% coverage is 80%.</p>
              </div>
            </div>

            <div className="card">
              <strong className="small">Block trust scores (shown to officers and used for confidence labels)</strong>
              <div className="tbl-wrap" style={{ marginTop: 8 }}>
                <table className="tbl">
                  <thead><tr><th>Block</th><th>District</th><th className="num">BSS onset</th><th className="num">BSS dry spell</th><th className="num">BSS heavy rain</th><th className="num">Trust</th></tr></thead>
                  <tbody>
                    {blocks.map((b) => (
                      <tr key={b.id}><td>{b.name}</td><td>{b.district}</td><td className="num">{b.bss_onset?.toFixed(2)}</td>
                        <td className="num">{b.bss_dry_spell?.toFixed(2)}</td><td className="num">{b.bss_heavy_rain?.toFixed(2)}</td>
                        <td className="num">{b.trust_score?.toFixed(2)}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <p className="tiny muted">Model {rep.model_version} · trained {rep.trained_at} · data: {Object.entries(rep.sources || {}).map(([k, v]) => `${k}: ${v}`).join(" · ")}</p>
          </div>
        )}
      </div>
    </>
  );
}
