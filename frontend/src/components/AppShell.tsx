"use client";

/**
 * StockMind AI — Application shell: sidebar navigation, top bar (search,
 * market clock, notifications, user menu), alert polling and toasts.
 */

import { ReactNode, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Activity,
  BarChart3,
  Bell,
  BellRing,
  Brain,
  FileText,
  Globe,
  LayoutDashboard,
  LogIn,
  LogOut,
  Menu,
  PieChart,
  Search,
  Settings as SettingsIcon,
  Sparkles,
  User as UserIcon,
  UserPlus,
  Wallet,
  X,
  Zap,
} from "lucide-react";
import { alertsAPI, healthAPI, marketAPI, signalsAPI } from "@/lib/api";
import { AppNotification, Tab, useAppStore } from "@/lib/store";
import { timeAgo } from "@/lib/format";
import SearchBox, { SearchBoxHandle } from "./SearchBox";
import { Toaster } from "./ui";

export const NAV_ITEMS: { id: Tab; label: string; icon: typeof LayoutDashboard }[] = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "scanner", label: "Market Scanner", icon: Search },
  { id: "predictions", label: "Predictions", icon: Brain },
  { id: "portfolio", label: "Portfolio", icon: Wallet },
  { id: "signals", label: "Daily Signals", icon: Zap },
  { id: "analytics", label: "Analytics", icon: BarChart3 },
  { id: "sectors", label: "Sector Map", icon: PieChart },
  { id: "news", label: "News & Events", icon: Globe },
  { id: "alerts", label: "Alerts", icon: Bell },
  { id: "prompt", label: "AI Prompt", icon: Sparkles },
  { id: "report", label: "Stock Report", icon: FileText },
  { id: "settings", label: "Settings", icon: SettingsIcon },
];

/** Navigate to a dashboard tab from anywhere in the app. */
export function useNavigateTab() {
  const router = useRouter();
  const pathname = usePathname();
  return useCallback(
    (tab: Tab) => {
      if (pathname === "/") {
        if (window.location.hash !== `#${tab}`) window.location.hash = tab;
        useAppStore.getState().setActiveTab(tab);
      } else {
        router.push(`/#${tab}`);
      }
      if (window.innerWidth < 1024) useAppStore.getState().setSidebarOpen(false);
    },
    [pathname, router]
  );
}

type UpstoxState = "checking" | "valid" | "invalid" | "not_configured" | "error" | "offline";

const UPSTOX_LABEL: Record<UpstoxState, { text: string; cls: string }> = {
  checking: { text: "…", cls: "badge-neutral" },
  valid: { text: "Connected", cls: "badge-bullish" },
  invalid: { text: "Token expired", cls: "badge-bearish" },
  not_configured: { text: "Not configured", cls: "badge-bearish" },
  error: { text: "Error", cls: "badge-bearish" },
  offline: { text: "Backend offline", cls: "badge-bearish" },
};

function Sidebar({ upstox, marketOpen }: { upstox: UpstoxState; marketOpen: boolean | null }) {
  const { activeTab, sidebarOpen, setSidebarOpen } = useAppStore();
  const pathname = usePathname();
  const navigate = useNavigateTab();
  const label = UPSTOX_LABEL[upstox];

  return (
    <>
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-30 lg:hidden"
          style={{ background: "rgba(0,0,0,0.5)" }}
          onClick={() => setSidebarOpen(false)}
          aria-hidden
        />
      )}
      <aside
        className={`fixed top-0 left-0 h-full z-40 transition-all duration-300 ease-out flex flex-col
          ${sidebarOpen ? "w-[240px] translate-x-0" : "w-[240px] -translate-x-full lg:translate-x-0 lg:w-[72px]"}`}
        style={{
          background: "rgba(10, 11, 15, 0.97)",
          borderRight: "1px solid var(--border-subtle)",
          backdropFilter: "blur(20px)",
        }}
        aria-label="Main navigation"
      >
        <div className="flex items-center justify-between gap-3 px-5 py-5 border-b" style={{ borderColor: "var(--border-subtle)" }}>
          <button className="flex items-center gap-3" onClick={() => navigate("dashboard")} aria-label="Go to dashboard">
            <div
              className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
              style={{ background: "linear-gradient(135deg, var(--accent-indigo), #7c3aed)" }}
            >
              <Brain size={20} className="text-white" />
            </div>
            {sidebarOpen && (
              <div className="animate-fade-in text-left">
                <h1 className="text-sm font-bold tracking-tight" style={{ color: "var(--text-primary)" }}>StockMind AI</h1>
                <p className="text-[10px] font-medium" style={{ color: "var(--text-muted)" }}>Intelligence Platform</p>
              </div>
            )}
          </button>
          {sidebarOpen && (
            // Wrapper carries lg:hidden: .btn-ghost's display would otherwise override the utility
            <span className="lg:hidden">
              <button className="btn-ghost" onClick={() => setSidebarOpen(false)} aria-label="Close menu">
                <X size={16} />
              </button>
            </span>
          )}
        </div>

        <nav className="px-3 py-4 flex flex-col gap-1 overflow-y-auto flex-1">
          {NAV_ITEMS.map((item) => {
            const isActive = pathname === "/" && activeTab === item.id;
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                onClick={() => navigate(item.id)}
                title={sidebarOpen ? undefined : item.label}
                aria-current={isActive ? "page" : undefined}
                className={`flex items-center gap-3 w-full rounded-lg transition-all duration-200 text-left
                  ${sidebarOpen ? "px-3 py-2.5" : "px-0 py-2.5 justify-center"}`}
                style={{
                  background: isActive ? "rgba(99, 102, 241, 0.12)" : "transparent",
                  color: isActive ? "var(--accent-indigo)" : "var(--text-secondary)",
                  border: isActive ? "1px solid rgba(99, 102, 241, 0.2)" : "1px solid transparent",
                }}
              >
                <Icon size={18} />
                {sidebarOpen && <span className="text-sm font-medium">{item.label}</span>}
              </button>
            );
          })}
        </nav>

        {sidebarOpen && (
          <div className="p-3">
            <button className="glass-card-static p-3 w-full text-left" onClick={() => navigate("settings")}>
              <div className="flex items-center gap-2 mb-2">
                <div className={`live-dot ${upstox === "valid" ? "" : "live-dot-disconnected"}`} />
                <span className="text-[11px] font-semibold" style={{ color: "var(--text-secondary)" }}>SYSTEM STATUS</span>
              </div>
              <div className="flex items-center justify-between text-[11px] mb-1" style={{ color: "var(--text-muted)" }}>
                <span>Upstox</span>
                <span className={`badge ${label.cls}`} style={{ fontSize: "9px", padding: "1px 6px" }}>{label.text}</span>
              </div>
              <div className="flex items-center justify-between text-[11px]" style={{ color: "var(--text-muted)" }}>
                <span>NSE</span>
                <span
                  className={`badge ${marketOpen ? "badge-bullish" : "badge-neutral"}`}
                  style={{ fontSize: "9px", padding: "1px 6px" }}
                >
                  {marketOpen == null ? "—" : marketOpen ? "Open" : "Closed"}
                </span>
              </div>
            </button>
          </div>
        )}
      </aside>
    </>
  );
}

function NotificationsMenu() {
  const { notifications, seenNotificationIds, markNotificationsSeen, isAuthenticated } = useAppStore();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const navigate = useNavigateTab();
  const unread = notifications.filter((n) => !seenNotificationIds.includes(n.id)).length;

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const toggle = () => {
    if (!open) markNotificationsSeen();
    setOpen(!open);
  };

  return (
    <div ref={ref} className="relative">
      <button className="btn-ghost relative" onClick={toggle} aria-label={`Notifications${unread ? ` (${unread} unread)` : ""}`}>
        {unread ? <BellRing size={18} /> : <Bell size={18} />}
        {unread > 0 && (
          <span
            className="absolute -top-1 -right-1 min-w-4 h-4 px-1 rounded-full text-[9px] font-bold flex items-center justify-center text-white"
            style={{ background: "var(--color-bearish)" }}
          >
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>
      {open && (
        <div className="popover right-0 mt-2 w-80">
          <div className="px-4 py-3 border-b flex items-center justify-between" style={{ borderColor: "var(--border-subtle)" }}>
            <span className="text-xs font-bold" style={{ color: "var(--text-primary)" }}>Notifications</span>
            <button className="text-[11px]" style={{ color: "var(--text-accent)" }} onClick={() => { setOpen(false); navigate("alerts"); }}>
              Manage alerts
            </button>
          </div>
          <div className="max-h-96 overflow-y-auto">
            {notifications.length === 0 ? (
              <p className="px-4 py-6 text-xs text-center" style={{ color: "var(--text-muted)" }}>
                {isAuthenticated ? "No notifications. Triggered alerts and market risk alerts appear here." : "Market risk alerts appear here. Sign in to get price alerts."}
              </p>
            ) : (
              notifications.map((n) => (
                <Link
                  key={n.id}
                  href={n.href || "/#alerts"}
                  onClick={() => setOpen(false)}
                  className="block px-4 py-3 border-b hover:bg-white/[0.03]"
                  style={{ borderColor: "var(--border-subtle)" }}
                >
                  <p className="text-xs font-semibold" style={{ color: "var(--text-primary)" }}>{n.title}</p>
                  <p className="text-[11px] mt-0.5" style={{ color: "var(--text-secondary)" }}>{n.body}</p>
                  <p className="text-[10px] mt-1" style={{ color: "var(--text-muted)" }}>{timeAgo(n.time)}</p>
                </Link>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function UserMenu() {
  const { user, isAuthenticated, logout, toast } = useAppStore();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const navigate = useNavigateTab();

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const initials = user
    ? (user.full_name || user.email).split(/[\s@.]+/).filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase()).join("")
    : "?";

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold"
        style={{ background: "linear-gradient(135deg, var(--accent-indigo), #7c3aed)", color: "white" }}
        aria-label="Account menu"
        aria-expanded={open}
      >
        {isAuthenticated ? initials : <UserIcon size={15} />}
      </button>
      {open && (
        <div className="popover right-0 mt-2 w-60">
          {isAuthenticated && user ? (
            <>
              <div className="px-4 py-3 border-b" style={{ borderColor: "var(--border-subtle)" }}>
                <p className="text-xs font-semibold truncate" style={{ color: "var(--text-primary)" }}>{user.full_name || "Analyst"}</p>
                <p className="text-[11px] truncate" style={{ color: "var(--text-muted)" }}>{user.email}</p>
              </div>
              <button className="popover-item" onClick={() => { setOpen(false); navigate("portfolio"); }}><Wallet size={14} /> Portfolio</button>
              <button className="popover-item" onClick={() => { setOpen(false); navigate("alerts"); }}><Bell size={14} /> Alerts</button>
              <button className="popover-item" onClick={() => { setOpen(false); navigate("settings"); }}><SettingsIcon size={14} /> Settings</button>
              <button
                className="popover-item"
                onClick={() => {
                  setOpen(false);
                  logout();
                  toast("Signed out", "info");
                }}
                style={{ color: "var(--color-bearish)" }}
              >
                <LogOut size={14} /> Sign out
              </button>
            </>
          ) : (
            <>
              <div className="px-4 py-3 border-b text-[11px]" style={{ borderColor: "var(--border-subtle)", color: "var(--text-muted)" }}>
                Browsing as guest. Sign in for alerts and your Upstox portfolio.
              </div>
              <Link href="/login" className="popover-item"><LogIn size={14} /> Sign in</Link>
              <Link href="/login?mode=register" className="popover-item"><UserPlus size={14} /> Create account</Link>
              <button className="popover-item" onClick={() => { setOpen(false); navigate("settings"); }}><SettingsIcon size={14} /> Settings</button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function TopBar({ marketOpen }: { marketOpen: boolean | null }) {
  const { sidebarOpen, setSidebarOpen } = useAppStore();
  const [time, setTime] = useState("");
  const router = useRouter();
  const searchRef = useRef<SearchBoxHandle>(null);

  useEffect(() => {
    const update = () =>
      setTime(
        new Date().toLocaleTimeString("en-IN", {
          hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false, timeZone: "Asia/Kolkata",
        })
      );
    update();
    const interval = setInterval(update, 1000);
    return () => clearInterval(interval);
  }, []);

  // Ctrl/Cmd + K focuses search
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <header
      className="sticky top-0 z-20 flex items-center justify-between gap-3 px-4 md:px-6 py-3 border-b"
      style={{ borderColor: "var(--border-subtle)", background: "rgba(10, 11, 15, 0.85)", backdropFilter: "blur(12px)" }}
    >
      <div className="flex items-center gap-3 flex-1 min-w-0">
        <button onClick={() => setSidebarOpen(!sidebarOpen)} className="btn-ghost" aria-label="Toggle menu">
          <Menu size={20} />
        </button>
        <SearchBox
          ref={searchRef}
          className="w-full max-w-[360px]"
          shortcutHint
          placeholder="Search stocks by name or symbol…"
          onSelect={(s) => router.push(`/stock/${encodeURIComponent(s)}`)}
        />
      </div>

      <div className="flex items-center gap-3 md:gap-4">
        <div className="hidden md:flex items-center gap-2 text-xs" style={{ color: "var(--text-muted)" }} title="NSE market status">
          <Activity size={14} style={{ color: marketOpen ? "var(--color-bullish)" : "var(--text-muted)" }} />
          <span className="font-mono">{time} IST</span>
        </div>
        <NotificationsMenu />
        <UserMenu />
      </div>
    </header>
  );
}

const ALERT_POLL_MS = 60_000;
const STATUS_POLL_MS = 120_000;

export default function AppShell({ children }: { children: ReactNode }) {
  const { sidebarOpen, isAuthenticated, settings, initFromStorage, verifySession, setNotifications, toast } = useAppStore();
  const [upstox, setUpstox] = useState<UpstoxState>("checking");
  const [marketOpen, setMarketOpen] = useState<boolean | null>(null);
  const riskRef = useRef<AppNotification[]>([]);
  const alertRef = useRef<AppNotification[]>([]);

  useEffect(() => {
    // initFromStorage trusts the stored token optimistically (no flash of guest UI on
    // load); verifySession immediately checks it's still actually valid and quietly
    // resets to guest if not — see store.ts for why this is split from the generic
    // 401 handler, which is reserved for a session dying mid-use, not a stale one.
    initFromStorage();
    verifySession();
  }, [initFromStorage, verifySession]);

  const publish = useCallback(
    () => setNotifications([...alertRef.current, ...riskRef.current]),
    [setNotifications]
  );

  // System + market status
  useEffect(() => {
    const load = () => {
      healthAPI
        .system()
        .then((res) => setUpstox(res.data.analytics_token as UpstoxState))
        .catch((err) => setUpstox(err?.response ? "error" : "offline"));
      marketAPI
        .status()
        .then((res) => setMarketOpen(/OPEN/.test(res.data?.status?.status || "") && !/CLOSE/.test(res.data?.status?.status || "")))
        .catch(() => setMarketOpen(null));
      signalsAPI
        .regime()
        .then((res) => {
          const ts = res.data?.timestamp || new Date().toISOString();
          riskRef.current = (res.data?.risk_alerts || []).map((a: any) => ({
            id: `risk:${a.trigger}`,
            title: "Market risk alert",
            body: `${a.trigger}. ${a.action || ""}`.trim(),
            time: ts,
            href: "/#analytics",
          }));
          publish();
        })
        .catch(() => {});
    };
    load();
    const timer = setInterval(load, STATUS_POLL_MS);
    return () => clearInterval(timer);
  }, [publish]);

  // Alert evaluation for signed-in users
  useEffect(() => {
    if (!isAuthenticated) {
      alertRef.current = [];
      publish();
      return;
    }
    const check = () => {
      if (document.visibilityState !== "visible") return;
      alertsAPI
        .check()
        .then((res) => {
          const describe = (a: any) =>
            `${a.alert_type.replace("_", " ")} ${a.alert_type.startsWith("price") ? "₹" : ""}${a.value}${a.alert_type.startsWith("change") ? "%" : ""}` +
            (a.triggered_price ? ` — hit at ₹${a.triggered_price}` : "");
          alertRef.current = (res.data.triggered || []).map((a: any) => ({
            id: `alert:${a.id}:${a.triggered_at}`,
            title: `${a.symbol} alert triggered`,
            body: a.message || describe(a),
            time: a.triggered_at,
            href: `/stock/${a.symbol}`,
          }));
          publish();
          for (const a of res.data.newly_triggered || []) {
            toast(`${a.symbol}: ${describe(a)}`, "info");
            if (settings.browserNotifications && "Notification" in window && Notification.permission === "granted") {
              new Notification(`${a.symbol} alert triggered`, { body: a.message || describe(a) });
            }
          }
        })
        .catch(() => {});
    };
    check();
    const timer = setInterval(check, ALERT_POLL_MS);
    return () => clearInterval(timer);
  }, [isAuthenticated, settings.browserNotifications, publish, toast]);

  return (
    <div className="min-h-screen" style={{ background: "var(--bg-primary)" }}>
      <Sidebar upstox={upstox} marketOpen={marketOpen} />
      <div className={`min-w-0 transition-all duration-300 ${sidebarOpen ? "lg:ml-[240px]" : "lg:ml-[72px]"}`}>
        <TopBar marketOpen={marketOpen} />
        <main className="p-4 md:p-6 max-w-[1600px] mx-auto">{children}</main>
      </div>
      <Toaster />
    </div>
  );
}
