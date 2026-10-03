/**
 * StockMind AI — Global State Store (Zustand)
 * Manages user auth, preferences, navigation, toasts and notifications.
 */

import { create } from "zustand";

/**
 * Decodes a JWT's payload locally (no network call) to check its own `exp`
 * claim. Used so initFromStorage can refuse to mark a self-evidently expired
 * token as "authenticated" in the first place — the alternative (an async
 * verifySession() call to the backend after the fact) loses a race against
 * every other component's own authenticated requests firing on mount with
 * that same stale token, each of which hits the generic 401 interceptor in
 * api.ts and forces the loud "session expired" redirect before the async
 * check can quietly clean up first.
 */
function isTokenExpired(token: string): boolean {
  try {
    const payload = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    if (!payload.exp) return false; // no exp claim — can't tell locally, let verifySession's network check decide
    return Date.now() >= payload.exp * 1000;
  } catch {
    return true; // malformed token — treat as invalid
  }
}

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  is_admin?: boolean;
}

export interface Settings {
  capital: number;
  riskPct: number;
  refreshSec: number; // 0 = auto-refresh off
  browserNotifications: boolean;
  usCapital: number; // paper-trading capital for the US Stocks tab (display only — no real sizing math yet)
}

export interface Toast {
  id: number;
  kind: "success" | "error" | "info";
  message: string;
}

export interface AppNotification {
  id: string;
  title: string;
  body: string;
  time: string;
  href?: string;
}

export const TABS = [
  "dashboard", "scanner", "predictions", "portfolio", "signals",
  "analytics", "sectors", "news", "alerts", "prompt", "report", "us_stocks", "settings",
] as const;
export type Tab = (typeof TABS)[number];

export const DEFAULT_SETTINGS: Settings = {
  capital: 200000,
  riskPct: 0.75,
  refreshSec: 60,
  browserNotifications: false,
  usCapital: 10000,
};

const SETTINGS_KEY = "stockmind_settings";
const SEEN_KEY = "stockmind_seen_notifications";

function readJSON<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? { ...fallback, ...JSON.parse(raw) } : fallback;
  } catch {
    return fallback;
  }
}

interface AppState {
  // Auth
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  hydrated: boolean;

  // Preferences
  settings: Settings;

  // Navigation
  sidebarOpen: boolean;
  activeTab: Tab;
  selectedSector: string | null;
  reportSymbol: string | null;

  // Feedback
  toasts: Toast[];
  notifications: AppNotification[];
  seenNotificationIds: string[];

  // Actions
  setUser: (user: User | null, token?: string) => void;
  logout: () => void;
  updateSettings: (patch: Partial<Settings>) => void;
  setSidebarOpen: (open: boolean) => void;
  setActiveTab: (tab: Tab) => void;
  setSelectedSector: (sector: string | null) => void;
  setReportSymbol: (symbol: string | null) => void;
  toast: (message: string, kind?: Toast["kind"]) => void;
  dismissToast: (id: number) => void;
  setNotifications: (items: AppNotification[]) => void;
  markNotificationsSeen: () => void;
  initFromStorage: () => void;
  verifySession: () => Promise<void>;
}

let toastId = 0;

export const useAppStore = create<AppState>((set, get) => ({
  user: null,
  token: null,
  isAuthenticated: false,
  hydrated: false,

  settings: DEFAULT_SETTINGS,

  sidebarOpen: true,
  activeTab: "dashboard",
  selectedSector: null,
  reportSymbol: null,

  toasts: [],
  notifications: [],
  seenNotificationIds: [],

  setUser: (user, token) => {
    if (token && typeof window !== "undefined") {
      localStorage.setItem("stockmind_token", token);
      localStorage.setItem("stockmind_user", JSON.stringify(user));
    }
    set({ user, token: token || null, isAuthenticated: !!user });
  },

  logout: () => {
    if (typeof window !== "undefined") {
      localStorage.removeItem("stockmind_token");
      localStorage.removeItem("stockmind_user");
    }
    set({ user: null, token: null, isAuthenticated: false, notifications: [] });
  },

  updateSettings: (patch) => {
    const settings = { ...get().settings, ...patch };
    try {
      localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
    } catch {}
    set({ settings });
  },

  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  setActiveTab: (tab) => set({ activeTab: tab }),
  setSelectedSector: (sector) => set({ selectedSector: sector }),
  setReportSymbol: (symbol) => set({ reportSymbol: symbol }),

  toast: (message, kind = "info") => {
    const id = ++toastId;
    set({ toasts: [...get().toasts, { id, kind, message }] });
    setTimeout(() => get().dismissToast(id), kind === "error" ? 7000 : 4000);
  },
  dismissToast: (id) => set({ toasts: get().toasts.filter((t) => t.id !== id) }),

  setNotifications: (items) => set({ notifications: items }),
  markNotificationsSeen: () => {
    const ids = Array.from(new Set([...get().seenNotificationIds, ...get().notifications.map((n) => n.id)])).slice(-200);
    try {
      localStorage.setItem(SEEN_KEY, JSON.stringify(ids));
    } catch {}
    set({ seenNotificationIds: ids });
  },

  initFromStorage: () => {
    if (typeof window === "undefined" || get().hydrated) return;
    const patch: Partial<AppState> = { hydrated: true };
    const token = localStorage.getItem("stockmind_token");
    const userStr = localStorage.getItem("stockmind_user");
    if (token && userStr) {
      if (isTokenExpired(token)) {
        // Quietly drop it and stay "guest" — no banner, no redirect. This is the common
        // case (the default JWT lifetime is 24h, so simply not opening the app for a day
        // hits this on every load) and deserves zero ceremony, not an "expired" alarm.
        localStorage.removeItem("stockmind_token");
        localStorage.removeItem("stockmind_user");
      } else {
        try {
          patch.user = JSON.parse(userStr);
          patch.token = token;
          patch.isAuthenticated = true;
        } catch {
          localStorage.removeItem("stockmind_token");
          localStorage.removeItem("stockmind_user");
        }
      }
    }
    patch.settings = readJSON(SETTINGS_KEY, DEFAULT_SETTINGS);
    try {
      patch.seenNotificationIds = JSON.parse(localStorage.getItem(SEEN_KEY) || "[]");
    } catch {}
    patch.sidebarOpen = window.innerWidth >= 1024;
    set(patch);
  },

  // initFromStorage already rejects a token that's self-evidently expired by its own
  // exp claim (isTokenExpired, above) — that's the common case and needs no network
  // round trip. This is the secondary check: a token that *looks* unexpired locally
  // but the backend has invalidated some other way (account deactivated, secret
  // rotated). Same quiet-reset-to-guest treatment, no banner, no redirect — only a
  // session dying *mid-use* should ever show "your session expired". Calls
  // authAPI.me() with skipAuthRedirect so this check can fail silently instead of
  // triggering the generic interceptor in api.ts.
  verifySession: async () => {
    const { token, isAuthenticated } = get();
    if (!token || !isAuthenticated) return;
    try {
      const { authAPI } = await import("./api");
      const res = await authAPI.me();
      set({ user: res.data });
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 401) get().logout();
    }
  },
}));

/** Portfolio params for API calls derived from user settings. */
export const portfolioParams = (s: Settings) => ({ capital: s.capital, risk_pct: s.riskPct });
