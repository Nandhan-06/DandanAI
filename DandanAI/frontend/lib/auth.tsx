"use client";
import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api, getToken, setToken } from "./api";

type Ctx = { user: any; status: any; loading: boolean; login: (e: string, p: string) => Promise<void>; register: (b: any) => Promise<any>; logout: () => Promise<void>; refresh: () => Promise<void>; toast: (m: string, kind?: "ok" | "err") => void };
const C = createContext<Ctx>(null as any);
export const useAuth = () => useContext(C);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<any>(null);
  const [status, setStatus] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [toasts, setToasts] = useState<{ id: number; m: string; kind: string }[]>([]);
  const toast = useCallback((m: string, kind: "ok" | "err" = "ok") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, m, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4500);
  }, []);
  const refresh = useCallback(async () => {
    api("/api/v1/system/status").then(setStatus).catch(() => setStatus({ unreachable: true }));
    if (!getToken()) { setUser(null); setLoading(false); return; }
    try { setUser(await api("/api/v1/auth/me")); } catch { setUser(null); }
    setLoading(false);
  }, []);
  useEffect(() => { refresh(); }, [refresh]);
  const login = async (email: string, password: string) => { const r = await api("/api/v1/auth/login", { body: { email, password } }); setToken(r.access_token); setUser(r.user); };
  const register = async (b: any) => { const r = await api("/api/v1/auth/register", { body: b }); setToken(r.access_token); setUser(r.user); return r; };
  const logout = async () => { try { await api("/api/v1/auth/logout", { method: "POST" }); } catch {} setToken(null); setUser(null); window.location.href = "/login"; };
  return (
    <C.Provider value={{ user, status, loading, login, register, logout, refresh, toast }}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 space-y-2" role="status" aria-live="polite">
        {toasts.map((t) => <div key={t.id} className={`rounded-md px-4 py-2 text-sm shadow-lg text-white ${t.kind === "err" ? "bg-red-600" : "bg-ink-900"}`}>{t.m}</div>)}
      </div>
    </C.Provider>
  );
}
