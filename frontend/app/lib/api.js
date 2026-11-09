// Varsha API client with a static fallback.
// Every read tries the FastAPI backend first; if it is unreachable, the same
// payload is read from /data/*.json (exported by the pipeline), so the app
// also works as a static site. Writes always need the backend.

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

let apiState = null; // null = unknown, true = reachable, false = offline

async function fetchWithTimeout(url, opts = {}, ms = 4000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), ms);
  try {
    return await fetch(url, { ...opts, signal: ctrl.signal });
  } finally {
    clearTimeout(timer);
  }
}

export async function apiAvailable() {
  if (apiState !== null) return apiState;
  try {
    const r = await fetchWithTimeout(`${API_URL}/health`, {}, 2500);
    apiState = r.ok;
  } catch {
    apiState = false;
  }
  return apiState;
}

const staticCache = {};
async function staticJSON(file) {
  if (!staticCache[file]) {
    staticCache[file] = fetch(`/data/${file}`).then((r) => {
      if (!r.ok) throw new Error(`Static data /data/${file} not found. Run scripts/bootstrap_demo.py`);
      return r.json();
    });
  }
  return staticCache[file];
}

async function apiGet(path) {
  const r = await fetchWithTimeout(`${API_URL}${path}`);
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json();
}

// read(path, fallback): fallback is an async function producing the same payload from static files
async function read(path, fallback) {
  if (await apiAvailable()) {
    try {
      return { data: await apiGet(path), source: "api" };
    } catch (e) {
      if (!fallback) throw e;
    }
  }
  if (!fallback) throw new Error("Backend API is not reachable");
  return { data: await fallback(), source: "static" };
}

export const getLatest = () => read("/api/v1/dashboard/latest", () => staticJSON("latest.json"));
export const getBlock = (id) =>
  read(`/api/v1/forecasts/block/${id}`, async () => (await staticJSON("blocks.json"))[String(id)]);
export const getPanchayat = (id) =>
  read(`/api/v1/forecasts/panchayat/${id}`, async () => (await staticJSON("panchayats.json"))[String(id)]);
export const getReplay = (year = 2023) =>
  read(`/api/v1/replay/bundle?year=${year}`, () => staticJSON("replay.json"));
export const getSkill = () => read("/api/v1/verification/skill", () => staticJSON("skill.json"));
export const getOutbox = (limit = 40) => read(`/api/v1/messaging/outbox?limit=${limit}`);
export const getRuns = () => read("/api/v1/pipeline/runs?limit=10");

export async function getBoundaries() {
  const [districts, blocks, panchayats] = await Promise.all(
    ["districts", "blocks", "panchayats"].map((n) => fetch(`/boundaries/${n}.geojson`).then((r) => r.json()))
  );
  return { districts, blocks, panchayats };
}

// ─── Writes ───
export function authHeader(creds) {
  if (!creds) return {};
  return { Authorization: "Basic " + btoa(unescape(encodeURIComponent(`${creds.user}:${creds.pass}`))) };
}

export async function apiSend(method, path, body, creds) {
  const r = await fetchWithTimeout(
    `${API_URL}${path}`,
    {
      method,
      headers: { "Content-Type": "application/json", ...authHeader(creds) },
      body: body === undefined ? undefined : JSON.stringify(body),
    },
    60000
  );
  const text = await r.text();
  let data;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { detail: text };
  }
  if (!r.ok) throw Object.assign(new Error(data.detail || `${r.status}`), { status: r.status, data });
  return data;
}

export async function apiGetAuth(path, creds) {
  return apiSend("GET", path, undefined, creds);
}
