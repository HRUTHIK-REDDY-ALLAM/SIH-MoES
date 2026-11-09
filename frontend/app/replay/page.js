"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import Header from "../components/Header";
import { ReplayChart } from "../components/Charts";
import { ActionBadge, SourceBadge } from "../components/Panels";
import { getBoundaries, getReplay } from "../lib/api";
import { CROPS, EVENT_BY_KEY, HORIZON_LABEL, ONSET_STATUS, fmtDate, pct, rainMax } from "../lib/format";

const RiskMap = dynamic(() => import("../components/RiskMap"), { ssr: false });

const REPLAY_EVENTS = ["onset", "false_onset", "dry_spell", "dry_spell_14d", "heavy_rain", "rainfall"];

export default function ReplayPage() {
  const [bnd, setBnd] = useState(null);
  const [rp, setRp] = useState(null);
  const [source, setSource] = useState(null);
  const [error, setError] = useState(null);
  const [i, setI] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [eventKey, setEventKey] = useState("dry_spell");
  const [h, setH] = useState(7);
  const [blockId, setBlockId] = useState(1);
  const timer = useRef(null);

  useEffect(() => {
    getBoundaries().then(setBnd);
    getReplay(2023).then(({ data, source }) => {
      setRp(data);
      setSource(source);
      const start = data.dates.indexOf("2023-06-08");
      setI(start >= 0 ? start : 0);
    }).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!playing || !rp) return;
    timer.current = setInterval(() => setI((x) => (x + 1 < rp.dates.length ? x + 1 : x)), 350);
    return () => clearInterval(timer.current);
  }, [playing, rp]);

  const ev = EVENT_BY_KEY[eventKey];
  const fieldName = ev.field;
  const bidx = rp ? rp.blocks.findIndex((b) => b.id === blockId) : -1;

  const values = useMemo(() => {
    if (!rp) return {};
    const arr = rp.forecast[String(h)]?.[fieldName]?.[i] || [];
    return Object.fromEntries(rp.blocks.map((b, j) => [b.id, arr[j]]));
  }, [rp, h, fieldName, i]);

  const overrides = useMemo(() => {
    if (!rp || eventKey !== "onset") return {};
    const st = rp.onset_status[i] || [];
    return Object.fromEntries(rp.blocks.map((b, j) => [b.id, st[j]]).filter(([, s]) => rp.onset_codes[s] === "established")
      .map(([id]) => [id, { color: "#0f766e", label: "established" }]));
  }, [rp, eventKey, i]);

  if (error) return (<><Header /><div className="page"><div className="notice error">{error}</div></div></>);
  if (!rp || !rp.dates?.length) return (<><Header /><div className="page"><p className="muted">Loading replay…</p></div></>);

  const date = rp.dates[i];
  const drv = rp.drivers[i] || {};
  const series = rp.forecast[String(h)][fieldName].map((row) => row[bidx]);
  const rain = rp.observed_rain.map((row) => row[bidx]);
  const status = rp.onset_status[i] || [];
  const statusCounts = status.reduce((acc, s) => ({ ...acc, [rp.onset_codes[s]]: (acc[rp.onset_codes[s]] || 0) + 1 }), {});
  const block = rp.blocks[bidx];
  const max = ev.unit === "mm" ? rainMax(h) : 1;
  const next = (n) => setI((x) => Math.max(0, Math.min(rp.dates.length - 1, x + n)));
  const futureRain = rain.slice(i, i + h).reduce((a, b) => a + (b || 0), 0);

  return (
    <>
      <Header right={<SourceBadge source={source} synthetic />} />
      <div className="dash">
        <div className="map-wrap">
          <div className="map-controls">
            <div className="seg glass">
              {REPLAY_EVENTS.map((k) => (
                <button key={k} className={eventKey === k ? "active" : ""} onClick={() => setEventKey(k)}>{EVENT_BY_KEY[k].short}</button>
              ))}
            </div>
            <div className="seg glass">
              {[7, 14, 21, 30].map((x) => <button key={x} className={h === x ? "active" : ""} onClick={() => setH(x)}>{x}d</button>)}
            </div>
          </div>
          {bnd && (
            <RiskMap districts={bnd.districts} blocks={bnd.blocks} panchayats={bnd.panchayats} level="block"
              values={values} palette={ev.palette} max={max} overrides={overrides}
              labelFor={(p, v, ov) => `<strong>${p.name}</strong><br/>${ov ? "Onset established" : ev.unit ? `${Math.round(v || 0)} mm` : pct(v)}`}
              selectedId={blockId} onSelect={(p) => setBlockId(p.id)} />
          )}
          <div className="legend glass" style={{ right: 12, left: 12, minWidth: 0 }}>
            <div className="row between">
              <strong>{fmtDate(date, { weekday: "short", day: "numeric", month: "short", year: "numeric" })}</strong>
              <span className="tiny muted">{ev.label} · {HORIZON_LABEL[h]}</span>
            </div>
            <input type="range" min={0} max={rp.dates.length - 1} value={i} onChange={(e) => setI(Number(e.target.value))} aria-label="Replay date" />
            <div className="row">
              <button className="btn btn-sm" onClick={() => next(-7)}>« 7d</button>
              <button className="btn btn-sm" onClick={() => next(-1)}>‹</button>
              <button className="btn btn-sm btn-primary" onClick={() => setPlaying(!playing)}>{playing ? "Pause" : "Play"}</button>
              <button className="btn btn-sm" onClick={() => next(1)}>›</button>
              <button className="btn btn-sm" onClick={() => next(7)}>7d »</button>
            </div>
          </div>
        </div>

        <aside className="side">
          <h2 className="panel-title">2023 Kharif replay</h2>
          <p className="small secondary" style={{ margin: "0 0 8px" }}>
            What Varsha would have forecast and advised each morning, using only data available that day — compared with the rain that followed.
          </p>
          <div className="synthetic-warning">Replay season rainfall is a scripted scenario modelled on the observed 2023 season (synthetic data).</div>

          <div className="section-title">Notable events (click to jump)</div>
          <div className="chips">
            {rp.events.map((e) => (
              <button key={e.date + e.type} className="chip" style={{ cursor: "pointer", background: "transparent" }}
                title={e.label} onClick={() => { const k = rp.dates.indexOf(e.date); if (k >= 0) setI(k); }}>
                {fmtDate(e.date, { day: "numeric", month: "short" })} · {e.type.replaceAll("_", " ")}
              </button>
            ))}
          </div>

          <div className="section-title">Drivers on {fmtDate(date, { day: "numeric", month: "short" })}</div>
          <div className="stat-grid">
            <div className="stat"><div className="l">MJO</div><div className="v" style={{ fontSize: "1rem" }}>Phase {drv.mjo_phase ?? "–"}</div><div className="tiny muted">amp {drv.mjo_amp ?? "–"}</div></div>
            <div className="stat"><div className="l">ONI</div><div className="v" style={{ fontSize: "1rem" }}>{drv.oni ?? "–"}</div></div>
            <div className="stat"><div className="l">DMI</div><div className="v" style={{ fontSize: "1rem" }}>{drv.dmi ?? "–"}</div></div>
          </div>
          <div className="row small" style={{ marginTop: 8 }}>
            {Object.entries(statusCounts).map(([k, n]) => (
              <span key={k} className="badge" style={{ color: ONSET_STATUS[k]?.color, borderColor: `${ONSET_STATUS[k]?.color}66` }}>{ONSET_STATUS[k]?.label?.split(" (")[0] || k}: {n}</span>
            ))}
          </div>

          <div className="section-title">{block?.name} ({block?.district})</div>
          <select value={blockId} onChange={(e) => setBlockId(Number(e.target.value))}>
            {rp.blocks.map((b) => <option key={b.id} value={b.id}>{b.name} — {b.district}</option>)}
          </select>
          <ReplayChart dates={rp.dates} rain={rain} prob={ev.unit ? series.map((v) => (v || 0) / max) : series}
            label={ev.unit ? `${ev.short} (scaled)` : `${ev.short} chance, ${HORIZON_LABEL[h]}`} markDate={date} events={rp.events} />
          <p className="small secondary" style={{ marginTop: 4 }}>
            Forecast on this day: <strong>{ev.unit ? `${Math.round(values[blockId] || 0)} mm` : pct(values[blockId])}</strong> · rain that actually fell in the next {h} days: <strong>{Math.round(futureRain)} mm</strong>
          </p>

          <div className="section-title">Advice issued that day (majority of panchayats)</div>
          {CROPS.map((c) => {
            const code = rp.advice[c.key]?.[i]?.[bidx];
            return (
              <div key={c.key} className="row between small" style={{ padding: "4px 0" }}>
                <span>{c.icon} {c.en}</span>
                {code != null ? <ActionBadge action={rp.action_codes[code]} /> : <span className="muted">–</span>}
              </div>
            );
          })}
        </aside>
      </div>
    </>
  );
}
