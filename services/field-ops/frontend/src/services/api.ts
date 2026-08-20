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

  // Equipment as found and as left — the Before/After table on the paper CORS
  // maintenance record. Free text on purpose: this is whatever is printed on
  // the hardware, not a key into a lookup. Distinct from antenna_model, which
  // is campaign-only and selects the height-reduction constants.
  equipment_changed?: boolean;
  receiver_model_before?: string;
  receiver_model_after?: string;
  receiver_serial_before?: string;
  receiver_serial_after?: string;
  receiver_firmware_before?: string;
  receiver_firmware_after?: string;
  antenna_type_before?: string;
  antenna_type_after?: string;
  antenna_part_number_before?: string;
  antenna_part_number_after?: string;
  antenna_serial_before?: string;
  antenna_serial_after?: string;
  antenna_height_before_m?: number;
  antenna_height_after_m?: number;
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

  // No usable detail from the server. A bare status code means nothing to
  // someone standing at a monument, and 5xx here is almost always "the API is
  // not answering" rather than anything they did — say that instead.
  if (status >= 500) return "The server is not responding.";
  if (status === 404) return "That request went somewhere the server does not recognise.";
  return `The server rejected the request (${status}).`;
}

// ── Base fetch ──────────────────────────────────────────────────────────────

/**
 * Request timeouts.
 *
 * `fetch` has none by default: a connection that opens and then goes quiet
 * hangs until the browser gives up, which can be minutes. That is not a corner
 * case for this app — it is the normal shape of a weak field link, and of a
 * captive portal at a barangay hall that accepts the TCP connection and never
 * answers. Without a ceiling the Sync button sits on "Syncing…" indefinitely
 * and the operator has no way to tell a slow sync from a dead one.
 *
 * Generous on purpose. These exist to end a *hung* request, not to cut short a
 * genuinely slow one — a 15 MB photo over 2G is legitimately slow, and killing
 * it would lose the upload this whole queue exists to protect.
 */
const JSON_TIMEOUT_MS = 45_000;
const UPLOAD_TIMEOUT_MS = 180_000;

export class TimeoutError extends Error {
  constructor(ms: number) {
    super(
      `No response after ${Math.round(ms / 1000)}s — the connection is up but ` +
        `the server is not answering. Your data is still saved on this device.`
    );
    this.name = "TimeoutError";
  }
}

/** fetch with a hard ceiling, translating an abort into a readable error. */
async function fetchWithTimeout(
  url: string,
  init: RequestInit,
  timeoutMs: number
): Promise<Response> {
  // AbortSignal.timeout is cleaner but leaves the reason as a bare
  // TimeoutError DOMException; wrapping keeps the message operator-readable.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new TimeoutError(timeoutMs);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string>),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };

  const resp = await fetchWithTimeout(apiUrl(path), { ...init, headers }, JSON_TIMEOUT_MS);

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

// ── Identity ────────────────────────────────────────────────────────────────

export interface Me {
  username: string;
  role: string;
}

export async function fetchMe(): Promise<Me> {
  return apiFetch<Me>("/me");
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
  const resp = await fetchWithTimeout(
    apiUrl(`/logsheets/${logsheetId}/photos`),
    { method: "POST", headers, body: form },
    UPLOAD_TIMEOUT_MS
  );
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


// ── /sheets — the end-of-day review ─────────────────────────────────────────

export interface SheetPhoto {
  id: number;
  filename: string | null;
  uploaded_at: string | null;
}

export interface Sheet {
  id: number;
  client_uuid: string;
  station_code: string;
  visit_date: string;
  monitoring_method: string | null;
  session_id: string | null;
  antenna_model: string | null;
  rinex_height_m: number | null;
  equipment_status: string | null;
  battery_voltage_v: number | null;
  equipment_changed: boolean | null;
  notes: string | null;
  created_at: string | null;
  synced_at: string | null;
  observers: string[];
  photos: SheetPhoto[];
}

export async function fetchSheets(): Promise<Sheet[]> {
  return apiFetch<Sheet[]>("/sheets");
}

/**
 * Fetch one photo's bytes as an object URL.
 *
 * Not an <img src="/api/v1/photos/1">: the token lives in localStorage and goes
 * out in an Authorization header, which a browser-issued image request cannot
 * carry. The alternatives were a token in the URL — a credential in something
 * that gets logged, shared and cached — or a presigned URL, which is a bearer
 * capability anyone can use until it expires. Fetching with the header and
 * handing React a blob keeps the credential where it belongs.
 *
 * The caller owns the returned URL and must revokeObjectURL it, or the bytes
 * stay in memory for the life of the document. On a field handset with a dozen
 * 4 MB photos that is the difference between a slow tab and a killed one.
 */
export async function fetchPhotoObjectUrl(photoId: number): Promise<string> {
  const token = getToken();
  const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
  const resp = await fetchWithTimeout(
    apiUrl(`/photos/${photoId}`),
    { headers },
    UPLOAD_TIMEOUT_MS
  );
  if (resp.status === 401) {
    clearToken();
    throw new ApiError(401, "Session expired — please log in again");
  }
  if (!resp.ok) {
    throw new ApiError(resp.status, `Could not load photo (${resp.status})`);
  }
  return URL.createObjectURL(await resp.blob());
}
