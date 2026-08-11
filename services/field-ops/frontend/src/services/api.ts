/**
 * Typed API client for the Field Ops FastAPI backend.
 *
 * All requests include the JWT Bearer token from localStorage.
 * On 401, the token is cleared and the user must re-authenticate.
 */

export interface Station {
  station_code: string;
  name: string | null;
  latitude: number | null;
  longitude: number | null;
  elevation: number | null;
  fault_segment: string | null;
  status: string | null;
}

export interface Staff {
  id: number;
  full_name: string;
  initials: string;
  role: string;
}

export interface LogSheetIn {
  client_uuid: string;
  station_code: string;
  monitoring_method?: string;  // "campaign" | "continuous"
  visit_date: string;          // ISO date "YYYY-MM-DD"
  arrival_time?: string;
  departure_time?: string;
  weather_conditions?: string;
  maintenance_performed?: string;
  equipment_status?: string;   // ok | issue_found | repaired
  notes?: string;
  observer_ids?: number[];
  // Continuous-only
  power_notes?: string;
  battery_voltage_v?: number;
  // Campaign-only
  antenna_model?: string;
  slant_n_m?: number;
  slant_e_m?: number;
  slant_s_m?: number;
  slant_w_m?: number;
  avg_slant_m?: number;
  rinex_height_m?: number;
  session_id?: string;
  utc_start?: string;
  utc_end?: string;
  bubble_centred?: boolean;
  plumbing_offset_mm?: number;
}

export interface LogSheetOut extends LogSheetIn {
  id: number;
  synced_at: string | null;
  created_at: string | null;
}

export interface Equipment {
  id: number;
  qr_code: string;
  equipment_type: string | null;
  serial_number: string | null;
  station_code: string | null;
  status: string | null;
  notes: string | null;
}

// ── API base ────────────────────────────────────────────────────────────────

/**
 * Empty by default, which yields same-origin relative paths (`/api/v1/...`).
 * That is what the Vite dev proxy expects, and what a Vercel rewrite expects —
 * and same-origin means no CORS preflight, which is one fewer round trip on a
 * connection that may be a single bar of signal.
 *
 * Set VITE_API_BASE_URL at build time only if the API is on another origin.
 */
const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

function apiUrl(path: string): string {
  return `${API_BASE}/api/v1${path}`;
}

// ── Token management ────────────────────────────────────────────────────────

const TOKEN_KEY = "field_ops_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

/**
 * Subscribers notified when the token is cleared by a 401.
 *
 * Without this, App reads `getToken()` once at mount and never learns that the
 * session died: the PWA keeps rendering the authenticated shell, every submit
 * silently diverts into the offline queue, and that queue can never drain
 * because it is the expired token failing. The operator fills sheets all
 * afternoon believing they are queued.
 */
const authListeners = new Set<() => void>();

export function onAuthCleared(fn: () => void): () => void {
  authListeners.add(fn);
  return () => authListeners.delete(fn);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
  authListeners.forEach((fn) => fn());
}

// ── Errors ──────────────────────────────────────────────────────────────────

/**
 * An HTTP error from the API, carrying the status code.
 *
 * The offline queue has to tell two failures apart that a bare Error cannot:
 * a network failure (expected in the field — retry forever, it will succeed
 * when signal returns) and a 4xx (a rejection that will fail identically on
 * every retry until the record itself changes). Retrying the second forever is
 * how a week of fieldwork sits in the queue with the Sync button appearing to
 * do nothing.
 */
export class ApiError extends Error {
  readonly status: number;
  /** Parsed `detail` from the response body, when the server sent a structured one. */
  readonly detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }

  /** True for a rejection that will not resolve itself on retry. */
  get isPermanent(): boolean {
    // 401 excluded: it is an auth failure, handled by clearToken/onAuthCleared,
    // and it *does* resolve once the operator logs in again. 408 and 429 are
    // explicitly transient.
    return (
      this.status >= 400 &&
      this.status < 500 &&
      this.status !== 401 &&
      this.status !== 408 &&
      this.status !== 429
    );
  }
}

/**
 * Turn a FastAPI error body into a readable sentence.
 *
 * `detail` is a string for simple HTTPExceptions, but a dict for the structured
 * ones (unknown staff ids) and a list for Pydantic validation failures. Showing
 * "[object Object]" to someone standing at a monument is not a message.
 */
function describeDetail(detail: unknown, status: number): string {
  if (typeof detail === "string") return detail;

  if (detail && typeof detail === "object") {
    const asRecord = detail as Record<string, unknown>;
    if (typeof asRecord.message === "string") return asRecord.message;
  }

  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => (d && typeof d === "object" ? (d as Record<string, unknown>).msg : null))
      .filter((m): m is string => typeof m === "string");
    if (msgs.length) return msgs.join("; ");
  }

  return `Request failed: ${status}`;
}

// ── Base fetch ──────────────────────────────────────────────────────────────

async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string>),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };

  const resp = await fetch(apiUrl(path), { ...init, headers });

  if (resp.status === 401) {
    clearToken();
    throw new ApiError(401, "Session expired — please log in again");
  }

  if (!resp.ok) {
    const body = (await resp.json().catch(() => ({}))) as { detail?: unknown };
    throw new ApiError(resp.status, describeDetail(body.detail, resp.status), body.detail);
  }

  return resp.json() as Promise<T>;
}

// ── Auth ────────────────────────────────────────────────────────────────────

export async function login(username: string, password: string): Promise<void> {
  const body = new URLSearchParams({ username, password });
  const resp = await fetch(apiUrl("/token"), {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });
  if (!resp.ok) throw new Error("Invalid credentials");
  const data = await resp.json();
  setToken(data.access_token);
}

// ── Stations ────────────────────────────────────────────────────────────────

export async function fetchStations(): Promise<Station[]> {
  return apiFetch<Station[]>("/stations");
}

// ── Staff ────────────────────────────────────────────────────────────────────

export async function fetchStaff(): Promise<Staff[]> {
  return apiFetch<Staff[]>("/staff");
}

// ── Logsheets ───────────────────────────────────────────────────────────────

/**
 * Submit one logsheet.
 *
 * The endpoint takes a LIST — deliberately, so the offline queue can flush a
 * whole day as one request. This wrapper previously POSTed a bare object, which
 * FastAPI rejected 422 ("Input should be a valid list"). The form's catch then
 * queued the record and told the operator "Saved offline", so the online path
 * had never once worked: every submission was mislabelled and its delivery
 * deferred until the app happened to reload.
 */
export async function submitLogSheet(record: LogSheetIn): Promise<LogSheetOut> {
  const created = await submitLogSheets([record]);
  if (created.length === 0) {
    // The endpoint re-fetches by client_uuid and returns every row it saw, so
    // an empty list means the record neither inserted nor already existed.
    // Throwing routes it to the offline queue rather than reporting success.
    throw new Error("Server accepted the request but returned no logsheet");
  }
  return created[0];
}

export async function submitLogSheets(records: LogSheetIn[]): Promise<LogSheetOut[]> {
  return apiFetch<LogSheetOut[]>("/logsheets", {
    method: "POST",
    body: JSON.stringify(records),
  });
}

export async function uploadLogSheetPhoto(logsheetId: number, photo: File): Promise<void> {
  const token = getToken();
  const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
  const form = new FormData();
  form.append("file", photo);
  const resp = await fetch(apiUrl(`/logsheets/${logsheetId}/photos`), {
    method: "POST",
    headers,
    body: form,
  });
  if (resp.status === 401) {
    clearToken();
    throw new ApiError(401, "Session expired — please log in again");
  }
  if (!resp.ok) {
    const body = (await resp.json().catch(() => ({}))) as { detail?: unknown };
    throw new ApiError(
      resp.status,
      typeof body.detail === "string" ? body.detail : `Photo upload failed: ${resp.status}`,
      body.detail
    );
  }
}

// ── Equipment ───────────────────────────────────────────────────────────────

export async function lookupEquipment(qrId: string): Promise<Equipment> {
  return apiFetch<Equipment>(`/equipment?qr_id=${encodeURIComponent(qrId)}`);
}
