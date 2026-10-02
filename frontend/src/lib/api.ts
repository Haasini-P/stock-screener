/**
 * StockMind AI — API Client
 * Centralized API client with auth headers and error handling.
 */

import axios, { AxiosInstance, AxiosError, InternalAxiosRequestConfig } from "axios";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000,
  headers: {
    "Content-Type": "application/json",
  },
});

// Request interceptor — attach JWT token
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    if (typeof window !== "undefined") {
      const token = localStorage.getItem("stockmind_token");
      if (token && config.headers) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor — an expired app session sends the user to sign in again
api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401 && typeof window !== "undefined") {
      const hadSession = !!localStorage.getItem("stockmind_token");
      localStorage.removeItem("stockmind_token");
      localStorage.removeItem("stockmind_user");
      if (hadSession && !window.location.pathname.includes("/login")) {
        const next = encodeURIComponent(window.location.pathname + window.location.search + window.location.hash);
        // Full reload on purpose: clears all in-memory state from the expired session
        // eslint-disable-next-line @next/next/no-location-assign-relative-destination
        window.location.href = `/login?next=${next}&expired=1`;
      }
    }
    return Promise.reject(error);
  }
);

/** Human-readable message from an API error. */
export function errorMessage(err: unknown, fallback = "Something went wrong. Please try again."): string {
  const e = err as AxiosError<any>;
  if (!e?.response) {
    if (e?.code === "ECONNABORTED") return "The request timed out. Please try again.";
    return `Cannot reach the backend at ${API_BASE_URL}. Is the server running?`;
  }
  const detail = e.response.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => d?.msg).filter(Boolean).join("; ") || fallback;
  if (detail?.message) return detail.action ? `${detail.message} ${detail.action}` : detail.message;
  return fallback;
}

export interface PortfolioParams {
  capital: number;
  risk_pct: number;
}

// ============================================================
// AUTH
// ============================================================

export const authAPI = {
  register: (email: string, password: string, fullName?: string) =>
    api.post("/api/auth/register", { email, password, full_name: fullName }),

  login: (email: string, password: string) =>
    api.post("/api/auth/login", { email, password }),

  me: () => api.get("/api/auth/me"),

  upstoxConnect: () => api.get("/api/auth/upstox/connect"),
  upstoxDisconnect: () => api.post("/api/auth/upstox/disconnect"),
  upstoxStatus: () => api.get("/api/auth/upstox/status"),
};

// ============================================================
// MARKET
// ============================================================

export const marketAPI = {
  overview: () => api.get("/api/market/overview"),
  status: () => api.get("/api/market/status"),
  sectors: () => api.get("/api/market/sectors"),
  movers: (limit = 5) => api.get("/api/market/movers", { params: { limit } }),
  news: (sector?: string) => api.get("/api/market/news", { params: { sector } }),

  quote: (symbol: string) => api.get(`/api/stocks/${encodeURIComponent(symbol)}/quote`),

  candles: (symbol: string, range: string, interval = "day") =>
    api.get(`/api/stocks/${encodeURIComponent(symbol)}/candles`, { params: { range, interval } }),

  fundamentals: (symbol: string) => api.get(`/api/stocks/${encodeURIComponent(symbol)}/fundamentals`),

  stockNews: (symbol: string, page = 1) =>
    api.get(`/api/stocks/${encodeURIComponent(symbol)}/news`, { params: { page } }),

  prediction: (symbol: string, horizon = "1D") =>
    api.get(`/api/stocks/${encodeURIComponent(symbol)}/prediction`, { params: { horizon } }),

  scanner: (params: Record<string, any>) =>
    api.get("/api/market/scanner", { params, timeout: 120000 }),

  searchInstruments: (query: string) =>
    api.get("/api/instruments/search", { params: { query } }),
};

// ============================================================
// SIGNALS
// ============================================================

export const signalsAPI = {
  regime: () => api.get("/api/signals/regime"),
  dailyList: (p: PortfolioParams, refresh = false) =>
    api.get("/api/signals/daily-list", { params: { ...p, refresh }, timeout: 120000 }),
  analyze: (symbol: string, p: PortfolioParams) =>
    api.get(`/api/signals/analyze/${encodeURIComponent(symbol)}`, { params: p }),
};

// ============================================================
// ALERTS
// ============================================================

export type AlertType = "price_above" | "price_below" | "change_above" | "change_below";

export const alertsAPI = {
  list: () => api.get("/api/alerts"),
  create: (body: { symbol: string; alert_type: AlertType; value: number; message?: string }) =>
    api.post("/api/alerts", body),
  update: (id: string, body: { is_active?: boolean; value?: number; message?: string }) =>
    api.put(`/api/alerts/${id}`, body),
  remove: (id: string) => api.delete(`/api/alerts/${id}`),
  check: () => api.post("/api/alerts/check"),
};

// ============================================================
// PORTFOLIO
// ============================================================

export const portfolioAPI = {
  overview: () => api.get("/api/portfolio"),
  holdings: () => api.get("/api/portfolio/holdings"),
  positions: () => api.get("/api/portfolio/positions"),
  pnl: (fromDate: string, toDate: string, segment = "EQ") =>
    api.get("/api/portfolio/pnl", {
      params: { from_date: fromDate, to_date: toDate, segment },
    }),
  funds: (segment = "SEC") =>
    api.get("/api/portfolio/funds", { params: { segment } }),
};

// ============================================================
// SYSTEM
// ============================================================

export const healthAPI = {
  health: () => api.get("/health"),
  ready: () => api.get("/ready", { validateStatus: () => true }),
  system: () => api.get("/api/system/status"),
};

export default api;
