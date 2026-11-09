"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import Header from "./components/Header";
import { RainFan, SeasonChart } from "./components/Charts";
import {
  ActionBadge, AdvisoryCard, ConfidenceTag, DriverChips, DriversCard, OnsetPill, ProbBars, RegimeLine, SourceBadge,
} from "./components/Panels";
import { getBlock, getBoundaries, getLatest, getPanchayat } from "./lib/api";
import {
  ACTION_COLOR, CROPS, EVENTS, EVENT_BY_KEY, HORIZONS, HORIZON_LABEL, ONSET_ESTABLISHED_COLOR, PALETTES, fmtDate, pct, rainMax,
} from "./lib/format";

const RiskMap = dynamic(() => import("./components/RiskMap"), { ssr: false });

const EVENT_FOR_EXPLAIN = { onset: "onset", false_onset: "false_onset", dry_spell: "dry_spell_7d", dry_spell_14d: "dry_spell_7d", heavy_rain: "heavy_rain", rainfall: "dry_spell_7d" };

export default function Dashboard() {
  const [bnd, setBnd] = useState(null);
  const [data, setData] = useState(null);
  const [source, setSource] = useState(null);
  const [error, setError] = useState(null);
  const [eventKey, setEventKey] = useState("dry_spell");
  const [h, setH] = useState(7);
  const [level, setLevel] = useState("block");
  const [sel, setSel] = useState(null);

  useEffect(() => {
    getBoundaries().then(setBnd).catch((e) => setError(String(e)));
    getLatest()
      .then(({ data, source }) => {
        setData(data);
        setSource(source);
        // Deep links: /?block=5 or /?panchayat=12 open the detail panel directly
        const q = new URLSearchParams(window.location.search);
        if (q.get("panchayat")) {
          setLevel("panchayat");
          setSel({ level: "panchayat", id: Number(q.get("panchayat")) });
        } else if (q.get("block")) {
          setSel({ level: "block", id: Number(q.get("block")) });
        }
      })
      .catch((e) => setError(e.message));
  }, []);

  const ev = EVENT_BY_KEY[eventKey];
  const max = ev.unit === "mm" ? rainMax(h) : 1;

  const values = useMemo(() => {
    if (!data) return {};
    const rows = level === "block" ? data.blocks : data.panchayats;
    return Object.fromEntries(rows.map((r) => [r.id, r.horizons?.[String(h)]?.[ev.field] ?? null]));
  }, [data, level, h, ev]);

  const overrides = useMemo(() => {
    if (!data || eventKey !== "onset") return {};
    const est = Object.fromEntries(data.blocks.filter((b) => b.onset_status === "established").map((b) => [b.id, b.onset_date]));
    if (level === "block") {
      return Object.fromEntries(Object.entries(est).map(([id, d]) => [id, { color: ONSET_ESTABLISHED_COLOR, label: `established ${d}` }]));
    }
    return Object.fromEntries(data.panchayats.filter((p) => est[p.block_id] !== undefined)
      .map((p) => [p.id, { color: ONSET_ESTABLISHED_COLOR, label: `established ${est[p.block_id]}` }]));
  }, [data, eventKey, level]);

  const labelFor = useCallback((props, v, ov) => {
    const val = ov ? `Onset ${ov.label}` : ev.unit === "mm" ? `${v == null ? "–" : Math.round(v)} mm` : pct(v);
    return `<strong>${props.name}</strong><br/>${ev.short} · ${HORIZON_LABEL[h]}: ${val}`;
  }, [ev, h]);

  const onSelect = useCallback((props) => setSel({ level: props.block_id && level === "panchayat" ? "panchayat" : "block", id: props.id }), [level]);

  const legendStops = PALETTES[ev.palette];

  return (
    <>
      <Header right={<SourceBadge source={source} synthetic={data?.is_synthetic} />} />
      <div className="dash">
        <div className="map-wrap">
          <div className="map-controls">
            <div className="seg glass" role="tablist" aria-label="Risk type">
              {EVENTS.map((e) => (
                <button key={e.key} className={eventKey === e.key ? "active" : ""} onClick={() => setEventKey(e.key)}>{e.short}</button>
              ))}
            </div>
            <div className="row">
              <div className="seg glass" aria-label="Horizon">
                {HORIZONS.map((x) => (
                  <button key={x} className={h === x ? "active" : ""} onClick={() => setH(x)}>{x === 7 ? "Wk 1" : x === 14 ? "Wk 2" : x === 21 ? "Wk 3" : "Wk 4"}</button>
                ))}
              </div>
              <div className="seg glass" aria-label="Level">
                {["block", "panchayat"].map((l) => (
                  <button key={l} className={level === l ? "active" : ""} onClick={() => { setLevel(l); setSel(null); }}>
                    {l === "block" ? "Blocks" : "Panchayats"}
                  </button>
                ))}
              </div>
            </div>
          </div>
          {bnd && (
            <RiskMap
              districts={bnd.districts} blocks={bnd.blocks} panchayats={bnd.panchayats} level={level}
              values={values} palette={ev.palette} max={max} overrides={overrides} labelFor={labelFor}
              selectedId={sel && sel.level === level ? sel.id : null} onSelect={onSelect}
            />
          )}
          <div className="legend glass">
            <div className="row between"><strong>{ev.label}</strong></div>
            <div className="tiny muted">{HORIZON_LABEL[h]} from {data ? fmtDate(data.issue_date) : "…"}</div>
            <div className="legend-bar" style={{ background: `linear-gradient(90deg, ${legendStops.join(",")})` }} />
            <div className="row between tiny muted"><span>0{ev.unit ? " mm" : "%"}</span><span>{ev.unit ? `${max}+ mm` : "100%"}</span></div>
            {eventKey === "onset" && <div className="row tiny" style={{ marginTop: 6 }}><span style={{ width: 12, height: 12, background: ONSET_ESTABLISHED_COLOR, display: "inline-block", borderRadius: 3 }} /> Onset established</div>}
          </div>
        </div>

        <aside className="side">
          {error && <div className="notice error">{error}</div>}
          {!data && !error && <p className="muted">Loading forecasts…</p>}
          {data && !sel && <Overview data={data} />}
          {data && sel?.level === "block" && (
            <BlockPanel id={sel.id} h={h} eventKey={eventKey} onBack={() => setSel(null)}
              onPanchayat={(id) => { setLevel("panchayat"); setSel({ level: "panchayat", id }); }} />
          )}
          {data && sel?.level === "panchayat" && (
            <PanchayatPanel id={sel.id} onBack={() => setSel(null)}
              onBlock={(id) => { setLevel("block"); setSel({ level: "block", id }); }} />
          )}
        </aside>
      </div>
    </>
  );
}

function Overview({ data }) {
  const counts = data.summary?.actions_by_crop || {};
  const onset = data.summary?.onset_status || {};
  const wk1 = data.skill?.hindcast;
  return (
    <div className="animate-fade-in">
      <h2 className="panel-title">Telangana pilot · {fmtDate(data.issue_date)}</h2>
      <p className="small secondary" style={{ margin: "0 0 10px" }}>
        Mahbubnagar · Nalgonda · Medak — {data.blocks.length} blocks, {data.panchayats.length} panchayats. Click a block or panchayat on the map.
      </p>
      {data.is_synthetic && (
        <div className="synthetic-warning">
          Rainfall for the pilot is generated by a teleconnection-driven simulator and boundaries are approximate.
          ENSO and IOD indices are real NOAA data; the 2023 MJO is a scenario matched to the replay season.
        </div>
      )}

      <div className="section-title">Onset status by block</div>
      <div className="stat-grid">
        {[["not_yet", "Not yet"], ["provisional", "Provisional"], ["established", "Established"], ["false_onset", "False onset"]].map(([k, l]) => (
          <div className="stat" key={k}><div className="v">{onset[k] || 0}</div><div className="l">{l}</div></div>
        ))}
      </div>

      <div className="section-title">Today&apos;s advice (panchayats per action)</div>
      {CROPS.map((c) => {
        const row = counts[c.key] || {};
        const total = Object.values(row).reduce((a, b) => a + b, 0) || 1;
        return (
          <div key={c.key} style={{ marginBottom: 8 }}>
            <div className="row between small"><span>{c.icon} {c.en}</span><span className="tiny muted">{Object.entries(row).map(([a, n]) => `${a} ${n}`).join(" · ")}</span></div>
            <div style={{ display: "flex", height: 10, borderRadius: 5, overflow: "hidden", marginTop: 4 }}>
              {Object.entries(row).map(([a, n]) => (
                <div key={a} title={`${a}: ${n}`} style={{ width: `${(100 * n) / total}%`, background: ACTION_COLOR[a] }} />
              ))}
            </div>
          </div>
        );
      })}
      <p className="tiny muted">{data.summary?.pending_advisories || 0} advisories waiting for officer approval · <Link href="/officer">open console</Link></p>

      <div className="section-title">Why — planetary drivers</div>
      <DriversCard drivers={data.drivers} />

      {wk1 && (
        <>
          <div className="section-title">How good is the forecast? (hindcast, week 1)</div>
          <div className="card small">
            {["onset", "dry_spell_7d", "heavy_rain"].map((e) => (
              <div className="row between" key={e}>
                <span className="secondary">{e.replaceAll("_", " ")}</span>
                <span className="mono">BSS {wk1[e]?.["7"]?.bss?.toFixed(2)} · AUC {wk1[e]?.["7"]?.auc?.toFixed(2)}</span>
              </div>
            ))}
            <p className="tiny muted" style={{ margin: "8px 0 0" }}>Leave-years-out hindcast {data.skill.train_years?.join("–")}; BSS &gt; 0 beats block climatology. <Link href="/skill">Full verification →</Link></p>
          </div>
        </>
      )}
      <p className="tiny muted" style={{ marginTop: 14 }}>Model {data.model_version}</p>
    </div>
  );
}

function useDetail(fetcher, id) {
  const [state, setState] = useState({ id: null, data: null, err: null });
  useEffect(() => {
    let live = true;
    fetcher(id)
      .then(({ data }) => live && setState({ id, data, err: null }))
      .catch((e) => live && setState({ id, data: null, err: e.message }));
    return () => { live = false; };
  }, [fetcher, id]);
  return state.id === id ? [state.data, state.err] : [null, null];
}

function BlockPanel({ id, h, eventKey, onBack, onPanchayat }) {
  const [d, err] = useDetail(getBlock, id);
  if (err) return <div className="notice error">{err}</div>;
  if (!d) return <p className="muted">Loading block…</p>;
  const f = d.horizons.find((x) => x.horizon_days === h) || d.horizons[0];
  const explainEvent = EVENT_FOR_EXPLAIN[eventKey];
  return (
    <div className="animate-fade-in">
      <button className="btn btn-sm" onClick={onBack}>← Overview</button>
      <h2 className="panel-title" style={{ marginTop: 10 }}>{d.name}</h2>
      <p className="small secondary" style={{ margin: "0 0 8px" }}>{d.district} district · block / mandal · {Math.round(d.elevation_m || 0)} m</p>
      <div className="row"><OnsetPill status={f.onset_status} date={f.onset_date} /><ConfidenceTag level={f.confidence_level} /></div>
      <div style={{ marginTop: 6 }}><RegimeLine current={f.current_regime} predicted={f.predicted_regime} probability={f.regime_probability} /></div>

      <div className="section-title">Chances · {HORIZON_LABEL[h]} ({fmtDate(f.valid_start, { day: "numeric", month: "short" })}–{fmtDate(f.valid_end, { day: "numeric", month: "short" })})</div>
      <ProbBars forecast={f} />

      <div className="card" style={{ marginTop: 10 }}>
        <p className="small" style={{ margin: "0 0 8px", lineHeight: 1.5 }}>{f.explanation_en}</p>
        <div className="tiny muted" style={{ marginBottom: 4 }}>Drivers of the {explainEvent.replaceAll("_", " ")} forecast (TreeSHAP):</div>
        <DriverChips drivers={f.top_drivers?.[explainEvent]} />
      </div>

      <div className="section-title">Rainfall outlook (cumulative)</div>
      <RainFan horizons={d.horizons} />

      <div className="section-title">Season so far</div>
      <SeasonChart series={d.season_timeseries} observations={d.observations} />
      {d.onset_record && (
        <p className="tiny muted">First onset rain {d.onset_record.first_onset || "–"}{d.onset_record.is_false_onset ? " (false onset)" : ""}; lasting onset {d.onset_record.true_onset || "not yet"}.</p>
      )}

      <div className="section-title">Panchayats</div>
      {d.panchayats.map((p) => (
        <div key={p.id} className="card" style={{ cursor: "pointer", padding: 10 }} onClick={() => onPanchayat(p.id)}>
          <div className="row between">
            <strong className="small">{p.name}</strong>
            <span className="tiny muted">{p.soil_type?.replaceAll("_", " ")} · {Math.round((p.irrigated_fraction || 0) * 100)}% irrigated</span>
          </div>
          <div className="row" style={{ marginTop: 6 }}>
            {p.advisories.map((a) => (
              <span key={a.crop} className="tiny row" style={{ gap: 4 }}>{CROPS.find((c) => c.key === a.crop)?.icon}<ActionBadge action={a.action} /></span>
            ))}
          </div>
        </div>
      ))}
      <p className="tiny muted">Block trust score {d.trust_score ?? "–"} (from hindcast skill).</p>
    </div>
  );
}

function PanchayatPanel({ id, onBack, onBlock }) {
  const [d, err] = useDetail(getPanchayat, id);
  if (err) return <div className="notice error">{err}</div>;
  if (!d) return <p className="muted">Loading panchayat…</p>;
  return (
    <div className="animate-fade-in">
      <div className="row"><button className="btn btn-sm" onClick={onBack}>← Overview</button>
        <button className="btn btn-sm" onClick={() => onBlock(d.block_id)}>Block: {d.block_name}</button></div>
      <h2 className="panel-title" style={{ marginTop: 10 }}>{d.name}</h2>
      <p className="small secondary" style={{ margin: "0 0 8px" }}>
        Gram panchayat · {d.soil_type?.replaceAll("_", " ")} soil · {Math.round((d.irrigated_fraction || 0) * 100)}% irrigated
      </p>
      <div className="row"><OnsetPill status={d.onset_status} /><ConfidenceTag level={d.confidence_level} /></div>
      <div className="section-title">Outlook</div>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr><th>Window</th><th className="num">Rain (median)</th><th className="num">Dry spell</th><th className="num">Heavy rain</th><th className="num">Onset</th></tr></thead>
          <tbody>
            {d.horizons.map((x) => (
              <tr key={x.horizon_days}>
                <td>{HORIZON_LABEL[x.horizon_days]}</td>
                <td className="num">{Math.round(x.rainfall_median)} mm <span className="tiny muted">({x.rainfall_anomaly_pct > 0 ? "+" : ""}{Math.round(x.rainfall_anomaly_pct)}%)</span></td>
                <td className="num">{pct(x.prob_dry_spell_7d)}</td>
                <td className="num">{pct(x.prob_heavy_rain)}</td>
                <td className="num">{pct(x.prob_onset)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="section-title">Crop advisories · {fmtDate(d.issue_date)}</div>
      {d.advisories.map((a) => <AdvisoryCard key={a.id} adv={a} defaultLang="te" showPhone={false} />)}
      <p className="tiny muted" style={{ marginTop: 10 }}>Farmers see this in the <Link href={`/farmer?p=${d.id}`}>farmer view</Link> and receive it by SMS / WhatsApp after officer approval.</p>
    </div>
  );
}
