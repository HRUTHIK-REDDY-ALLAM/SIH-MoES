"use client";

import { useEffect, useMemo, useState } from "react";
import Header from "../components/Header";
import { SourceBadge } from "../components/Panels";
import { apiAvailable, apiSend, getLatest, getPanchayat } from "../lib/api";
import { CROPS, fmtDate } from "../lib/format";

const T = {
  en: {
    title: "Your village advisory", block: "Block (mandal)", village: "Gram panchayat", crop: "Crop",
    survival: "Chance seedlings survive if sown today", stage: "Crop stage", outlook: "Rain outlook",
    days: "days", rain: "Rain", dry: "Dry spell", heavy: "Heavy rain", ask: "Did it rain in your village today?",
    yes: "Yes, it rained", no: "No rain", thanks: "Thank you! Your report improves the forecast.",
    offline: "Reports need the Varsha server (backend offline in this demo).", subscribe: "Get these advisories on your phone",
    phone: "Mobile number", sms: "SMS", whatsapp: "WhatsApp", register: "Subscribe", registered: "Registered. Advisories will come after officer approval.",
    issued: "Issued", lang: "Language", notsown: "not sown",
  },
  te: {
    title: "మీ గ్రామ వ్యవసాయ సలహా", block: "మండలం", village: "గ్రామ పంచాయతీ", crop: "పంట",
    survival: "ఈరోజు విత్తితే మొలకలు బతికే అవకాశం", stage: "పంట దశ", outlook: "వర్ష సూచన",
    days: "రోజులు", rain: "వర్షం", dry: "పొడి వాతావరణం", heavy: "భారీ వర్షం", ask: "ఈరోజు మీ గ్రామంలో వర్షం పడిందా?",
    yes: "అవును, పడింది", no: "పడలేదు", thanks: "ధన్యవాదాలు! మీ సమాచారం సూచనను మెరుగుపరుస్తుంది.",
    offline: "సమాచారం పంపడానికి వర్ష సర్వర్ అవసరం (ఈ డెమోలో సర్వర్ అందుబాటులో లేదు).", subscribe: "ఈ సలహాలు మీ ఫోన్‌కు పొందండి",
    phone: "మొబైల్ నంబర్", sms: "SMS", whatsapp: "వాట్సాప్", register: "నమోదు చేయండి", registered: "నమోదు అయింది. అధికారి ఆమోదం తర్వాత సలహాలు వస్తాయి.",
    issued: "జారీ", lang: "భాష", notsown: "విత్తలేదు",
  },
  hi: {
    title: "आपके गांव की कृषि सलाह", block: "ब्लॉक (मंडल)", village: "ग्राम पंचायत", crop: "फसल",
    survival: "आज बोने पर पौध बचने की संभावना", stage: "फसल अवस्था", outlook: "बारिश का पूर्वानुमान",
    days: "दिन", rain: "बारिश", dry: "सूखा", heavy: "भारी बारिश", ask: "क्या आज आपके गांव में बारिश हुई?",
    yes: "हाँ, हुई", no: "नहीं हुई", thanks: "धन्यवाद! आपकी जानकारी पूर्वानुमान बेहतर बनाती है।",
    offline: "रिपोर्ट भेजने के लिए वर्षा सर्वर चाहिए (इस डेमो में सर्वर बंद है)।", subscribe: "यह सलाह अपने फोन पर पाएं",
    phone: "मोबाइल नंबर", sms: "SMS", whatsapp: "व्हाट्सऐप", register: "पंजीकरण करें", registered: "पंजीकरण हो गया। अधिकारी की मंजूरी के बाद सलाह आएगी।",
    issued: "जारी", lang: "भाषा", notsown: "बुवाई नहीं",
  },
};

const ACTION_WORD = {
  SOW: { en: "Sow now", te: "ఇప్పుడు విత్తండి", hi: "अभी बुवाई करें" },
  WAIT: { en: "Wait — do not sow yet", te: "ఇంకా విత్తవద్దు", hi: "अभी बुवाई न करें" },
  SWITCH: { en: "Switch crop", te: "పంట మార్చండి", hi: "फसल बदलें" },
  PROTECT: { en: "Protect your crop", te: "పంటను కాపాడండి", hi: "फसल बचाएं" },
  IRRIGATE: { en: "Give protective irrigation", te: "రక్షణ తడి ఇవ్వండి", hi: "जीवन-रक्षक सिंचाई करें" },
  CONSERVE: { en: "Conserve soil moisture", te: "నేల తేమను కాపాడండి", hi: "मिट्टी की नमी बचाएं" },
  PREPARE: { en: "Heavy rain — prepare", te: "భారీ వర్షం — సిద్ధంగా ఉండండి", hi: "भारी बारिश — तैयार रहें" },
  ALERT: { en: "Very heavy rain alert", te: "అతి భారీ వర్ష హెచ్చరిక", hi: "अति भारी वर्षा चेतावनी" },
  RESOW_ALERT: { en: "Resowing may be needed", te: "మళ్ళీ విత్తాల్సి రావచ్చు", hi: "दोबारा बुवाई करनी पड़ सकती है" },
  NORMAL: { en: "Normal — continue work", te: "సాధారణం — పనులు కొనసాగించండి", hi: "सामान्य — काम जारी रखें" },
};
const ICON = { SOW: "🌱", WAIT: "⏳", SWITCH: "🔄", PROTECT: "🛡️", IRRIGATE: "💧", CONSERVE: "🌾", PREPARE: "🌧️", ALERT: "⚠️", RESOW_ALERT: "♻️", NORMAL: "✅" };

function load(key, dflt) {
  try { return localStorage.getItem(key) ?? dflt; } catch { return dflt; }
}
function save(key, v) {
  try { localStorage.setItem(key, v); } catch { /* storage unavailable */ }
}

export default function FarmerPage() {
  const [lang, setLang] = useState("te");
  const [latest, setLatest] = useState(null);
  const [source, setSource] = useState(null);
  const [blockId, setBlockId] = useState(null);
  const [pid, setPid] = useState(null);
  const [crop, setCrop] = useState("cotton");
  const [detailState, setDetailState] = useState({ pid: null, data: null });
  const [online, setOnline] = useState(false);
  const [note, setNote] = useState(null);
  const [phone, setPhone] = useState("");
  const [channel, setChannel] = useState("sms");
  const t = T[lang];

  useEffect(() => {
    apiAvailable().then(setOnline);
    getLatest().then(({ data, source }) => {
      setLang(load("varsha.lang", "te"));
      setCrop(load("varsha.crop", "cotton"));
      setLatest(data);
      setSource(source);
      const qp = new URLSearchParams(window.location.search).get("p");
      const want = Number(qp || load("varsha.panchayat", "")) || data.panchayats[0]?.id;
      const p = data.panchayats.find((x) => x.id === want) || data.panchayats[0];
      setPid(p.id);
      setBlockId(p.block_id);
    });
  }, []);

  useEffect(() => {
    if (!pid) return;
    save("varsha.panchayat", String(pid));
    getPanchayat(pid).then(({ data }) => setDetailState({ pid, data }));
  }, [pid]);
  const detail = detailState.pid === pid ? detailState.data : null;

  const villages = useMemo(() => (latest?.panchayats || []).filter((p) => p.block_id === blockId), [latest, blockId]);
  const adv = detail?.advisories?.find((a) => a.crop === crop);

  async function report(rain) {
    if (!online) return setNote(t.offline);
    try {
      await apiSend("POST", "/api/v1/feedback/report", { panchayat_id: pid, report_date: detail.issue_date, rain_today: rain, language: lang });
      setNote(t.thanks);
    } catch (e) {
      setNote(e.message);
    }
  }

  async function subscribe(e) {
    e.preventDefault();
    if (!online) return setNote(t.offline);
    try {
      await apiSend("POST", "/api/v1/messaging/subscribers", { phone, panchayat_id: pid, crops: [crop], language: lang, channel });
      setNote(t.registered);
    } catch (err) {
      setNote(err.message);
    }
  }

  return (
    <>
      <Header right={<SourceBadge source={source} synthetic={latest?.is_synthetic} />} />
      <div className="page-narrow">
        <div className="row between">
          <h2 className="panel-title">{t.title}</h2>
          <div className="seg" aria-label={t.lang}>
            {[["te", "తెలుగు"], ["hi", "हिन्दी"], ["en", "EN"]].map(([k, l]) => (
              <button key={k} className={lang === k ? "active" : ""} onClick={() => { setLang(k); save("varsha.lang", k); }}>{l}</button>
            ))}
          </div>
        </div>

        {latest && (
          <div className="stack" style={{ marginTop: 12 }}>
            <label className="field">{t.block}
              <select value={blockId || ""} onChange={(e) => {
                const b = Number(e.target.value);
                setBlockId(b);
                setPid(latest.panchayats.find((p) => p.block_id === b)?.id);
              }}>
                {latest.blocks.map((b) => <option key={b.id} value={b.id}>{b.name} ({b.district})</option>)}
              </select>
            </label>
            <label className="field">{t.village}
              <select value={pid || ""} onChange={(e) => setPid(Number(e.target.value))}>
                {villages.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </label>
            <div>
              <div className="small secondary" style={{ marginBottom: 4 }}>{t.crop}</div>
              <div className="seg" style={{ width: "100%" }}>
                {CROPS.map((c) => (
                  <button key={c.key} className={crop === c.key ? "active" : ""} style={{ flex: 1 }}
                    onClick={() => { setCrop(c.key); save("varsha.crop", c.key); }}>{c.icon} {c[lang]}</button>
                ))}
              </div>
            </div>
          </div>
        )}

        {!detail && <p className="muted" style={{ marginTop: 16 }}>…</p>}
        {adv && (
          <div className={`action-card ac-${adv.action}`} style={{ marginTop: 16 }}>
            <div className="tiny muted">{t.issued} {fmtDate(detail.issue_date)} · {detail.name}</div>
            <div className="aw">{ICON[adv.action]} {ACTION_WORD[adv.action]?.[lang]}</div>
            <p>{adv.status === "approved" && adv.edited_message && lang === "en" ? adv.edited_message : adv[`message_${lang}`]}</p>
            <div className="row small secondary" style={{ marginTop: 10 }}>
              {adv.seedling_survival_prob != null && <span>🌱 {t.survival}: <strong>{Math.round(adv.seedling_survival_prob * 100)}%</strong></span>}
            </div>
            <div className="tiny muted" style={{ marginTop: 4 }}>{t.stage}: {adv.crop_stage === "not_sown" ? t.notsown : adv.crop_stage?.replace("_", " ")}</div>
          </div>
        )}

        {detail && (
          <>
            <div className="section-title">{t.outlook}</div>
            <div className="weeks">
              {detail.horizons.map((x) => (
                <div className="week" key={x.horizon_days}>
                  <div className="tiny muted">{x.horizon_days} {t.days}</div>
                  <div className="big">🌧️ {Math.round(x.rainfall_median)}<span className="tiny"> mm</span></div>
                  <div className="tiny" style={{ color: "#b91c1c" }}>{t.dry} {Math.round(x.prob_dry_spell_7d * 100)}%</div>
                  <div className="tiny" style={{ color: "#1d4ed8" }}>{t.heavy} {Math.round(x.prob_heavy_rain * 100)}%</div>
                </div>
              ))}
            </div>

            <div className="section-title">{t.ask}</div>
            <div className="row" style={{ flexWrap: "nowrap" }}>
              <button className="btn btn-success btn-lg" onClick={() => report(true)}>☔ {t.yes}</button>
              <button className="btn btn-lg" onClick={() => report(false)}>☀️ {t.no}</button>
            </div>

            <div className="section-title">{t.subscribe}</div>
            <form className="row" onSubmit={subscribe}>
              <input type="tel" placeholder={t.phone} value={phone} onChange={(e) => setPhone(e.target.value)} required
                pattern="^\+?[0-9\- ]{10,16}$" className="grow" />
              <div className="seg">
                {["sms", "whatsapp"].map((c) => <button type="button" key={c} className={channel === c ? "active" : ""} onClick={() => setChannel(c)}>{t[c]}</button>)}
              </div>
              <button className="btn btn-primary" type="submit">{t.register}</button>
            </form>
            {note && <div className="notice" style={{ marginTop: 12 }}>{note}</div>}
            {latest?.is_synthetic && <p className="tiny muted" style={{ marginTop: 14 }}>Prototype: synthetic rainfall and approximate village boundaries. Telugu/Hindi texts await agronomist review.</p>}
          </>
        )}
      </div>
    </>
  );
}
