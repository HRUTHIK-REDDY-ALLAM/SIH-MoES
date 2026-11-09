"use client";

import { Fragment, useState } from "react";
import { ACTION_LABEL, CROPS, EVENTS, ONSET_STATUS, PALETTES, REGIME, pct } from "../lib/format";

export function ActionBadge({ action }) {
  return <span className={`badge act-${action}`}>{ACTION_LABEL[action] || action}</span>;
}

export function OnsetPill({ status, date }) {
  const s = ONSET_STATUS[status] || { label: status || "–", color: "#64748b" };
  return (
    <span className="badge" style={{ background: `${s.color}22`, color: s.color, borderColor: `${s.color}66` }}>
      Onset: {s.label}
      {date && status !== "not_yet" ? ` · ${date}` : ""}
    </span>
  );
}

export function ConfidenceTag({ level }) {
  if (!level) return null;
  return <span className={`small conf-${level}`}>● {level} confidence</span>;
}

export function DriversCard({ drivers }) {
  if (!drivers || !drivers.date) return null;
  const mjoColor = drivers.mjo_impact?.startsWith("break") ? "#b91c1c" : drivers.mjo_impact?.startsWith("active") ? "#047857" : "#12355b";
  return (
    <div className="card">
      <div className="row between">
        <strong className="small">Large-scale drivers</strong>
        <span className="tiny muted">as known on {drivers.date}</span>
      </div>
      <div className="stat-grid" style={{ marginTop: 10 }}>
        <div className="stat">
          <div className="l">ENSO (ONI)</div>
          <div className="v" style={{ fontSize: "1.1rem" }}>{drivers.oni > 0 ? "+" : ""}{drivers.oni}</div>
          <div className="tiny secondary">{drivers.enso_phase}</div>
        </div>
        <div className="stat">
          <div className="l">IOD (DMI)</div>
          <div className="v" style={{ fontSize: "1.1rem" }}>{drivers.dmi > 0 ? "+" : ""}{drivers.dmi}</div>
          <div className="tiny secondary">{drivers.iod_phase}</div>
        </div>
        <div className="stat">
          <div className="l">MJO</div>
          <div className="v" style={{ fontSize: "1.1rem", color: mjoColor }}>Phase {drivers.mjo_phase}</div>
          <div className="tiny secondary">amp {drivers.mjo_amplitude} {drivers.mjo_active ? "(active)" : "(weak)"}</div>
        </div>
      </div>
      <p className="small secondary" style={{ margin: "10px 0 0" }}>{drivers.mjo_description}</p>
      {drivers.sources && (
        <p className="tiny muted" style={{ margin: "6px 0 0" }}>
          Sources: {Object.entries(drivers.sources).filter(([k]) => ["oni", "dmi", "mjo"].includes(k)).map(([k, v]) => `${k.toUpperCase()}: ${v}`).join(" · ")}
        </p>
      )}
    </div>
  );
}

const BAR_EVENTS = ["onset", "false_onset", "dry_spell", "dry_spell_14d", "heavy_rain"];

export function ProbBars({ forecast }) {
  if (!forecast) return null;
  const clim = {
    prob_onset: forecast.clim_prob_onset,
    prob_dry_spell_7d: forecast.clim_prob_dry_spell_7d,
    prob_heavy_rain: forecast.clim_prob_heavy_rain,
  };
  return (
    <div>
      {EVENTS.filter((e) => BAR_EVENTS.includes(e.key)).map((e) => {
        const v = forecast[e.field];
        const color = PALETTES[e.palette][3];
        return (
          <div className="pbar" key={e.key} title={clim[e.field] != null ? `Climatology ${pct(clim[e.field])}` : ""}>
            <span className="secondary">{e.short}</span>
            <div className="pbar-track">
              <div className="pbar-fill" style={{ width: `${Math.round((v || 0) * 100)}%`, background: color }} />
              {clim[e.field] != null && <div className="pbar-clim" style={{ left: `${Math.round(clim[e.field] * 100)}%` }} />}
            </div>
            <span className="mono" style={{ textAlign: "right" }}>{pct(v)}</span>
          </div>
        );
      })}
      <p className="tiny muted" style={{ margin: "4px 0 0" }}>Dark tick = usual chance for this time of year (climatology).</p>
    </div>
  );
}

export function DriverChips({ drivers }) {
  if (!drivers?.length) return null;
  return (
    <div className="chips">
      {drivers.map((d) => (
        <span key={d.group} className={`chip ${d.contribution > 0 ? "up" : "down"}`} title={`log-odds ${d.contribution}`}>
          {d.contribution > 0 ? "▲" : "▼"} {d.group}
        </span>
      ))}
    </div>
  );
}

export function RegimeLine({ current, predicted, probability }) {
  return (
    <span className="small secondary">
      Now: <strong>{REGIME[current] || current || "–"}</strong>
      {predicted && predicted !== "pre_onset" && (
        <> · outlook: <strong>{REGIME[predicted] || predicted}</strong> ({pct(probability)})</>
      )}
    </span>
  );
}

const LANG_LABEL = { en: "English", te: "తెలుగు", hi: "हिन्दी" };

export function AdvisoryCard({ adv, defaultLang = "en", showPhone = false }) {
  const [lang, setLang] = useState(defaultLang);
  const crop = CROPS.find((c) => c.key === adv.crop);
  const msg = adv.status === "approved" && adv.edited_message && lang === "en" ? adv.edited_message : adv[`message_${lang}`];
  return (
    <div className="adv-card">
      <div className="row between">
        <div className="row">
          <span>{crop?.icon}</span>
          <strong>{crop?.en || adv.crop}</strong>
          <ActionBadge action={adv.action} />
        </div>
        <div className="seg">
          {Object.keys(LANG_LABEL).map((l) => (
            <button key={l} className={lang === l ? "active" : ""} onClick={() => setLang(l)}>{LANG_LABEL[l]}</button>
          ))}
        </div>
      </div>
      <p className="adv-msg">{msg}</p>
      <div className="row small muted">
        <span>Stage: {adv.crop_stage?.replace("_", " ")}</span>
        {adv.seedling_survival_prob != null && <span>· Seedling survival if sown now: {pct(adv.seedling_survival_prob)}</span>}
        <span>· {adv.status}</span>
      </div>
      <details style={{ marginTop: 6 }}>
        <summary>Why? Rule <code>{adv.rule_id}</code> and the numbers behind it</summary>
        <div className="kv">
          {Object.entries(adv.reasoning || {}).filter(([, v]) => typeof v !== "object" || v === null).map(([k, v]) => (
            <Fragment key={k}><span>{k.replaceAll("_", " ")}</span><span>{v === null ? "–" : String(v)}</span></Fragment>
          ))}
        </div>
      </details>
      {showPhone && <div style={{ marginTop: 10 }}><PhonePreview messages={[{ body: adv[`sms_${lang}`], direction: "out", channel: "sms" }]} title="SMS preview" /></div>}
    </div>
  );
}

export function PhonePreview({ messages = [], title = "Varsha" }) {
  return (
    <div className="phone">
      <div className="phone-top"><span>{title}</span><span className="tiny muted">mock gateway</span></div>
      <div className="phone-body">
        {messages.length === 0 && <span className="tiny muted">No messages yet.</span>}
        {messages.map((m, i) => (
          <div key={m.id || i} className={`bubble ${m.direction === "in" ? "in" : "out"}`}>
            {m.body}
            <span className="meta">
              {m.channel || "sms"} {m.language ? `· ${m.language}` : ""} {m.phone ? `· ${m.phone}` : ""}
              {m.created_at ? ` · ${m.created_at.slice(0, 16)}` : ""}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function SourceBadge({ source, synthetic }) {
  return (
    <div className="row">
      {synthetic && <span className="synthetic-warning hide-sm">Synthetic rainfall &amp; boundaries</span>}
      <span className="status-pill" title={source === "api" ? "Live from the FastAPI backend" : "Static snapshot (backend offline)"}>
        {source === "api" ? "● live API" : source === "static" ? "○ static snapshot" : "…"}
      </span>
    </div>
  );
}
