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
// AI PROMPT
// ============================================================

export const promptAPI = {
  get: () => api.get("/api/prompt"),
  update: (content: string) => api.put("/api/prompt", { content }),
  suggest: () => api.post("/api/prompt/suggest"),
};

// ============================================================
// ALERTS
// ============================================================

export type AlertType = "price_above" | "price_below" | "change_above" | "change_below" | "signal_buy";

export const alertsAPI = {
  list: () => api.get("/api/alerts"),
  create: (body: { symbol: string; alert_type: AlertType; value?: number; message?: string }) =>
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
// BROKER ACCOUNTS & ORDERS
// ============================================================

export interface BrokerAccount {
  id: string;
  provider: "upstox" | "kite";
  nickname: string | null;
  account_user_name: string | null;
  account_email: string | null;
  is_connected: boolean;
  is_active: boolean;
  connected_at: string | null;
}

export const accountsAPI = {
  list: () => api.get<BrokerAccount[]>("/api/accounts"),
  connectUpstox: (nickname?: string) => api.get("/api/accounts/upstox/connect", { params: { nickname } }),
  connectKite: (nickname?: string) => api.get("/api/accounts/kite/connect", { params: { nickname } }),
  activate: (id: string) => api.post(`/api/accounts/${id}/activate`),
  remove: (id: string) => api.delete(`/api/accounts/${id}`),
};

export type OrderSide = "BUY" | "SELL";

export interface OrderPayload {
  account_id: string;
  symbol: string;
  transaction_type: OrderSide;
  quantity: number;
  order_type: "MARKET" | "LIMIT";
  product: "DELIVERY" | "INTRADAY";
  price?: number;
  target_price?: number;
  stop_price?: number;
  trailing_amount?: number;
}

export interface TrackedBracket {
  id: string;
  provider: "upstox" | "kite";
  symbol: string;
  transaction_type: OrderSide;
  quantity: number;
  entry_price: number | null;
  target_price: number | null;
  stop_price: number | null;
  trailing_amount: number | null;
  status: "ACTIVE" | "TRIGGERED" | "CANCELLED" | "ERROR";
  last_error: string | null;
  last_trailed_at: string | null;
  created_at: string | null;
}

export const ordersAPI = {
  place: (payload: OrderPayload) => api.post("/api/orders/place", payload),
  listBrackets: () => api.get<TrackedBracket[]>("/api/orders/brackets"),
  cancelBracket: (id: string) => api.delete(`/api/orders/brackets/${id}`),
};

export interface BrokerCredentialStatus {
  client_id: string;
  redirect_uri: string;
  has_secret: boolean;
  configured: boolean;
  source: "database" | "env";
}

export interface BrokerCredentialUpdate {
  client_id: string;
  client_secret?: string;
  redirect_uri: string;
}

export const brokerSettingsAPI = {
  get: () => api.get<{ upstox: BrokerCredentialStatus; kite: BrokerCredentialStatus }>("/api/settings/brokers"),
  updateUpstox: (payload: BrokerCredentialUpdate) => api.put("/api/settings/brokers/upstox", payload),
  updateKite: (payload: BrokerCredentialUpdate) => api.put("/api/settings/brokers/kite", payload),
};

export interface ModelPricing {
  input: number;
  output: number;
}

export interface AISettingsStatus {
  has_key: boolean;
  model: string;
  configured: boolean;
  pricing: Record<string, ModelPricing>;
}

export interface AICommentaryResult {
  content: string;
  model: string;
  cached: boolean;
  chart_included: boolean;
  generated_at: string;
}

export interface AIBatchCommentaryResult {
  content: string;
  model: string;
  cached: boolean;
  symbols: string[];
  generated_at: string;
}

export const aiSettingsAPI = {
  get: () => api.get<AISettingsStatus>("/api/settings/ai"),
  update: (payload: { api_key?: string; model: string }) => api.put("/api/settings/ai", payload),
};

export const MAX_BATCH_SYMBOLS = 8;

export const aiAPI = {
  getCommentary: (symbol: string) => api.post<AICommentaryResult>(`/api/ai/commentary/${encodeURIComponent(symbol)}`),
  getBatchCommentary: (symbols: string[]) => api.post<AIBatchCommentaryResult>("/api/ai/commentary/batch", { symbols }),
};

// ============================================================
// MODEL TRAINING
// ============================================================

export interface TrainingRunStatus {
  id: string;
  status: "running" | "completed" | "failed";
  started_at: string | null;
  completed_at: string | null;
  training_data_rows: number | null;
  test_data_rows: number | null;
  metrics: { by_horizon: Record<string, { accuracy: number; log_loss: number; brier_up: number; train_rows: number; test_rows: number }>; avg_accuracy: number } | null;
  error_message: string | null;
  model_version_id: string | null;
}

export interface ModelVersionSummary {
  id: string;
  version: string;
  status: "training" | "validating" | "champion" | "challenger" | "retired";
  is_champion: boolean;
  accuracy: number | null;
  log_loss_score: number | null;
  brier_score: number | null;
  training_data_start: string | null;
  training_data_end: string | null;
  created_at: string | null;
  promoted_at: string | null;
  metrics_by_horizon: Record<string, { accuracy: number; log_loss: number; brier_up: number; train_rows: number; test_rows: number }> | null;
}

export const mlAPI = {
  train: (payload?: { symbols?: string[]; lookback_days?: number }) => api.post<{ run_id: string }>("/api/ml/train", payload || {}),
  getRun: (runId: string) => api.get<TrainingRunStatus>(`/api/ml/train/${runId}`),
  listModels: () => api.get<ModelVersionSummary[]>("/api/ml/models"),
  promote: (modelVersionId: string) => api.post(`/api/ml/models/${modelVersionId}/promote`),
};

// ============================================================
// SYSTEM
// ============================================================

export const healthAPI = {
  health: () => api.get("/health"),
  ready: () => api.get("/ready", { validateStatus: () => true }),
  system: () => api.get("/api/system/status"),
};

export type DevService = "backend" | "frontend" | "both";

export const systemAPI = {
  restart: (service: DevService) => api.post<{ status: string; service: DevService }>("/api/system/restart", { service }),
};

// ============================================================
// WATCHLIST (scanner "added on" dates + short/mid/long segregation)
// ============================================================

export type WatchlistTerm = "short" | "mid" | "long";

export interface WatchlistEntry {
  symbol: string;
  term: WatchlistTerm;
  source: "auto" | "manual";
  bucket: string | null;
  added_by: string | null;
  added_at: string;
}

export const watchlistAPI = {
  list: () => api.get<{ items: WatchlistEntry[]; terms: WatchlistTerm[] }>("/api/watchlist"),
  add: (symbol: string, term: WatchlistTerm) => api.post<WatchlistEntry>("/api/watchlist", { symbol, term }),
  setTerm: (symbol: string, term: WatchlistTerm) => api.put<WatchlistEntry>(`/api/watchlist/${encodeURIComponent(symbol)}`, { term }),
  remove: (symbol: string) => api.delete(`/api/watchlist/${encodeURIComponent(symbol)}`),
};

export default api;
