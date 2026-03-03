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

// ── Token management ────────────────────────────────────────────────────────

const TOKEN_KEY = "field_ops_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

// ── Base fetch ──────────────────────────────────────────────────────────────

async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string>),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };

  const resp = await fetch(`/api/v1${path}`, { ...init, headers });

  if (resp.status === 401) {
    clearToken();
    throw new Error("Session expired — please log in again");
  }

  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({}));
    throw new Error(detail.detail ?? `Request failed: ${resp.status}`);
  }

  return resp.json() as Promise<T>;
}

// ── Auth ────────────────────────────────────────────────────────────────────

export async function login(username: string, password: string): Promise<void> {
  const body = new URLSearchParams({ username, password });
  const resp = await fetch("/api/v1/token", {
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

export async function submitLogSheet(record: LogSheetIn): Promise<LogSheetOut> {
  return apiFetch<LogSheetOut>("/logsheets", {
    method: "POST",
    body: JSON.stringify(record),
  });
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
  const resp = await fetch(`/api/v1/logsheets/${logsheetId}/photos`, {
    method: "POST",
    headers,
    body: form,
  });
  if (resp.status === 401) {
    clearToken();
    throw new Error("Session expired — please log in again");
  }
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({})) as { detail?: string };
    throw new Error(detail.detail ?? `Photo upload failed: ${resp.status}`);
  }
}

// ── Equipment ───────────────────────────────────────────────────────────────

export async function lookupEquipment(qrId: string): Promise<Equipment> {
  return apiFetch<Equipment>(`/equipment?qr_id=${encodeURIComponent(qrId)}`);
}
