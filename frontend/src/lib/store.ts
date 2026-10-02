/**
 * StockMind AI — Global State Store (Zustand)
 * Manages user auth, preferences, navigation, toasts and notifications.
 */

import { create } from "zustand";

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
  "analytics", "sectors", "news", "alerts", "settings",
] as const;
export type Tab = (typeof TABS)[number];

export const DEFAULT_SETTINGS: Settings = {
  capital: 200000,
  riskPct: 0.75,
  refreshSec: 60,
  browserNotifications: false,
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
  toast: (message: string, kind?: Toast["kind"]) => void;
  dismissToast: (id: number) => void;
  setNotifications: (items: AppNotification[]) => void;
  markNotificationsSeen: () => void;
  initFromStorage: () => void;
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
      try {
        patch.user = JSON.parse(userStr);
        patch.token = token;
        patch.isAuthenticated = true;
      } catch {
        localStorage.removeItem("stockmind_token");
        localStorage.removeItem("stockmind_user");
      }
    }
    patch.settings = readJSON(SETTINGS_KEY, DEFAULT_SETTINGS);
    try {
      patch.seenNotificationIds = JSON.parse(localStorage.getItem(SEEN_KEY) || "[]");
    } catch {}
    patch.sidebarOpen = window.innerWidth >= 1024;
    set(patch);
  },
}));

/** Portfolio params for API calls derived from user settings. */
export const portfolioParams = (s: Settings) => ({ capital: s.capital, risk_pct: s.riskPct });
