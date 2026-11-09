"use client";

import { useCallback, useEffect, useState } from "react";
import Header from "../components/Header";
import { ActionBadge, PhonePreview } from "../components/Panels";
import { apiAvailable, apiGetAuth, apiSend, getLatest, getOutbox, getRuns } from "../lib/api";
import { ACTION_LABEL, CROPS, fmtDate, pct } from "../lib/format";

function loadCreds() {
  try { return JSON.parse(sessionStorage.getItem("varsha.officer") || "null"); } catch { return null; }
}

export default function OfficerPage() {
  const [online, setOnline] = useState(null);
  const [creds, setCreds] = useState(null);
  const [form, setForm] = useState({ user: "officer", pass: "" });
  const [loginErr, setLoginErr] = useState(null);

  useEffect(() => {
    apiAvailable().then((ok) => {
      setCreds(loadCreds());
      setOnline(ok);
    });
  }, []);

  async function login(e) {
    e.preventDefault();
    try {
      await apiGetAuth("/api/v1/officer/whoami", form);
      sessionStorage.setItem("varsha.officer", JSON.stringify(form));
      setCreds(form);
      setLoginErr(null);
    } catch (err) {
      setLoginErr(err.status === 401 ? "Wrong username or password" : err.message);
    }
  }

  return (
    <>
      <Header right={creds && <button className="btn btn-sm" onClick={() => { sessionStorage.removeItem("varsha.officer"); setCreds(null); }}>Log out {creds.user}</button>} />
      <div className="page">
        <h2 className="panel-title">Extension officer console</h2>
        <p className="small secondary">Review machine-generated advisories, edit or reject them, approve, and dispatch to farmers by SMS / WhatsApp.</p>
        {online === false && (
          <div className="notice error" style={{ marginTop: 12 }}>
            The officer console needs the Varsha API. Start it with <code>uvicorn backend.main:app --reload</code> (port 8000).
          </div>
        )}
        {online && !creds && (
          <form className="card" style={{ maxWidth: 380, marginTop: 16 }} onSubmit={login}>
            <div className="stack">
              <label className="field">Username<input type="text" value={form.user} onChange={(e) => setForm({ ...form, user: e.target.value })} /></label>
              <label className="field">Password<input type="password" value={form.pass} onChange={(e) => setForm({ ...form, pass: e.target.value })} /></label>
              <button className="btn btn-primary" type="submit">Log in</button>
              {loginErr && <div className="notice error">{loginErr}</div>}
              <p className="tiny muted" style={{ margin: 0 }}>Demo credentials come from OFFICER_USERNAME / OFFICER_PASSWORD in .env.</p>
            </div>
          </form>
        )}
        {online && creds && <Console creds={creds} />}
      </div>
    </>
  );
}

function Console({ creds }) {
  const [stats, setStats] = useState(null);
  const [items, setItems] = useState([]);
  const [count, setCount] = useState(0);
  const [blocks, setBlocks] = useState([]);
  const [filter, setFilter] = useState({ district_id: "", block_id: "", action: "" });
  const [outbox, setOutbox] = useState([]);
  const [runs, setRuns] = useState([]);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const [runDate, setRunDate] = useState("2023-08-08");

  const refresh = useCallback(async () => {
    const q = new URLSearchParams(Object.entries(filter).filter(([, v]) => v)).toString();
    const [s, p, o, r] = await Promise.all([
      apiGetAuth("/api/v1/officer/stats", creds),
      apiGetAuth(`/api/v1/officer/pending?limit=60&${q}`, creds),
      getOutbox(30).then((x) => x.data).catch(() => ({ messages: [] })),
      getRuns().then((x) => x.data).catch(() => ({ runs: [] })),
    ]);
    setStats(s);
    setItems(p.advisories);
    setCount(p.count);
    setOutbox(o.messages);
    setRuns(r.runs);
  }, [creds, filter]);

  useEffect(() => {
    getLatest().then(({ data }) => setBlocks(data.blocks));
  }, []);
  useEffect(() => {
    let cancelled = false;
    Promise.resolve().then(() => !cancelled && refresh()).catch((e) => setMsg(e.message));
    return () => { cancelled = true; };
  }, [refresh]);

  async function act(fn, label) {
    setBusy(true);
    setMsg(null);
    try {
      const res = await fn();
      setMsg(`${label}: ${JSON.stringify(res)}`);
      await refresh();
    } catch (e) {
      setMsg(`${label} failed: ${e.message}`);
    } finally {
      setBusy(false);
    }
  }

  const districts = [...new Map(blocks.map((b) => [b.district_id, b.district])).entries()];

  return (
    <div className="stack" style={{ marginTop: 16 }}>
      {stats && (
        <div className="stat-grid">
          <div className="stat"><div className="v">{stats.pending}</div><div className="l">Pending</div></div>
          <div className="stat"><div className="v">{stats.approved}</div><div className="l">Approved</div></div>
          <div className="stat"><div className="v">{stats.rejected}</div><div className="l">Rejected</div></div>
          <div className="stat"><div className="v" style={{ fontSize: "1rem" }}>{fmtDate(stats.latest_issue_date)}</div><div className="l">Latest issue</div></div>
        </div>
      )}
      {msg && <div className="notice">{msg}</div>}

      <div className="grid-2">
        <div>
          <div className="card">
            <div className="row">
              <select value={filter.district_id} onChange={(e) => setFilter({ ...filter, district_id: e.target.value, block_id: "" })}>
                <option value="">All districts</option>
                {districts.map(([id, n]) => <option key={id} value={id}>{n}</option>)}
              </select>
              <select value={filter.block_id} onChange={(e) => setFilter({ ...filter, block_id: e.target.value })}>
                <option value="">All blocks</option>
                {blocks.filter((b) => !filter.district_id || String(b.district_id) === filter.district_id).map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
              </select>
              <select value={filter.action} onChange={(e) => setFilter({ ...filter, action: e.target.value })}>
                <option value="">All actions</option>
                {Object.keys(ACTION_LABEL).map((a) => <option key={a} value={a}>{ACTION_LABEL[a]}</option>)}
              </select>
            </div>
            <div className="row" style={{ marginTop: 10 }}>
              <button className="btn btn-success" disabled={busy || !count} onClick={() => act(() => apiSend("POST", `/api/v1/officer/approve-all${filter.district_id ? `?district_id=${filter.district_id}` : ""}`, undefined, creds), "Approve all")}>
                Approve all pending{filter.district_id ? " in district" : ""} ({count})
              </button>
              <button className="btn btn-primary" disabled={busy} onClick={() => act(() => apiSend("POST", "/api/v1/officer/dispatch", undefined, creds), "Dispatch")}>
                Dispatch approved → SMS / WhatsApp
              </button>
            </div>
          </div>

          <div className="section-title">Pending review ({items.length} of {count})</div>
          {items.length === 0 && <p className="muted small">Nothing pending.</p>}
          {items.map((a) => <ReviewCard key={a.id} a={a} creds={creds} onDone={refresh} />)}
        </div>

        <div>
          <div className="section-title" style={{ marginTop: 0 }}>Outbox (mock gateway)</div>
          <PhonePreview messages={outbox.slice(0, 12)} title="Delivered messages" />
          <div className="section-title">Run the pipeline</div>
          <div className="card">
            <div className="row">
              <input type="date" value={runDate} onChange={(e) => setRunDate(e.target.value)} />
              <button className="btn" disabled={busy} onClick={() => act(() => apiSend("POST", `/api/v1/pipeline/run?run_date=${runDate}`, undefined, creds), "Pipeline")}>
                {busy ? "Running…" : "Run forecast + advisories"}
              </button>
            </div>
            <p className="tiny muted" style={{ margin: "8px 0 0" }}>Produces block and panchayat forecasts and pending advisories for that date (Kharif season dates).</p>
          </div>
          <div className="section-title">Recent pipeline runs</div>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr><th>Date</th><th>Status</th><th className="num">Advisories</th></tr></thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id} title={r.message}><td>{r.run_date}</td><td>{r.status}</td><td className="num">{r.n_advisories}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

function ReviewCard({ a, creds, onDone }) {
  const [lang, setLang] = useState("en");
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(a.message_en);
  const [err, setErr] = useState(null);
  const crop = CROPS.find((c) => c.key === a.crop);

  async function review(action) {
    try {
      await apiSend("POST", `/api/v1/officer/review/${a.id}`, { action, edited_message: action === "edit" ? text : undefined }, creds);
      onDone();
    } catch (e) {
      setErr(e.message);
    }
  }

  return (
    <div className="adv-card">
      <div className="row between">
        <div className="row">
          <strong className="small">{a.panchayat_name}</strong>
          <span className="tiny muted">{a.block_name} · {fmtDate(a.issue_date)}</span>
        </div>
        <div className="row"><span>{crop?.icon} {crop?.en}</span><ActionBadge action={a.action} /></div>
      </div>
      {!editing ? (
        <>
          <div className="seg" style={{ marginTop: 8 }}>
            {["en", "te", "hi"].map((l) => <button key={l} className={lang === l ? "active" : ""} onClick={() => setLang(l)}>{l.toUpperCase()}</button>)}
          </div>
          <p className="adv-msg">{a[`message_${lang}`]}</p>
        </>
      ) : (
        <textarea value={text} onChange={(e) => setText(e.target.value)} style={{ marginTop: 8 }} />
      )}
      <div className="row tiny muted">
        <span>rule {a.rule_id}</span>
        {a.seedling_survival_prob != null && <span>· survival {pct(a.seedling_survival_prob)}</span>}
        <span>· {a.confidence_level} confidence</span>
      </div>
      <details style={{ marginTop: 6 }}>
        <summary>Decision inputs</summary>
        <div className="kv">
          {Object.entries(a.reasoning || {}).filter(([, v]) => typeof v !== "object" || v === null).map(([k, v]) => (
            <span key={k} style={{ display: "contents" }}><span>{k.replaceAll("_", " ")}</span><span>{v === null ? "–" : String(v)}</span></span>
          ))}
        </div>
      </details>
      <div className="row" style={{ marginTop: 8 }}>
        {!editing && <button className="btn btn-success btn-sm" onClick={() => review("approve")}>Approve</button>}
        {!editing && <button className="btn btn-sm" onClick={() => setEditing(true)}>Edit</button>}
        {editing && <button className="btn btn-success btn-sm" onClick={() => review("edit")}>Save &amp; approve</button>}
        {editing && <button className="btn btn-sm" onClick={() => setEditing(false)}>Cancel</button>}
        <button className="btn btn-danger btn-sm" onClick={() => review("reject")}>Reject</button>
      </div>
      {err && <div className="notice error" style={{ marginTop: 6 }}>{err}</div>}
    </div>
  );
}
