export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const KEY = "dandanai_token";
export const getToken = () => (typeof window === "undefined" ? null : localStorage.getItem(KEY));
export const setToken = (t: string | null) => (t ? localStorage.setItem(KEY, t) : localStorage.removeItem(KEY));

export class ApiError extends Error { status: number; constructor(m: string, s: number) { super(m); this.status = s; } }

export async function api<T = any>(path: string, opts: { method?: string; body?: any; form?: FormData; raw?: boolean } = {}): Promise<T> {
  const headers: Record<string, string> = {};
  const t = getToken();
  if (t) headers.Authorization = `Bearer ${t}`;
  let body: any;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(opts.body); }
  let res: Response;
  try { res = await fetch(`${API}${path}`, { method: opts.method || (body ? "POST" : "GET"), headers, body }); }
  catch { throw new ApiError("Cannot reach the API. Is the backend running at " + API + "?", 0); }
  if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/api/v1/auth/login")) { setToken(null); window.location.href = "/login"; }
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j); } catch {}
    throw new ApiError(msg, res.status);
  }
  if (opts.raw) return res as any;
  if (res.status === 204) return undefined as any;
  return res.json();
}

export async function download(path: string, filename: string) {
  const res: Response = await api(path, { raw: true });
  const blob = await res.blob();
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = filename; a.click(); URL.revokeObjectURL(a.href);
}
