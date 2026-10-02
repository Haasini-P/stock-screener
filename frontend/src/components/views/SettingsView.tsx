"use client";

import { useState } from "react";
import Link from "next/link";
import { Bell, Database, KeyRound, LogOut, Save, Server, ShieldCheck, SlidersHorizontal, User } from "lucide-react";
import { API_BASE_URL, healthAPI } from "@/lib/api";
import { DEFAULT_SETTINGS, useAppStore } from "@/lib/store";
import { useApi } from "@/lib/useApi";
import { fmtINR } from "@/lib/format";
import { useNavigateTab } from "../AppShell";
import { Card, KeyValue, LoadingRows, PageHeader, SectionHeader } from "../ui";

const TOKEN_STATUS: Record<string, { label: string; cls: string; help: string }> = {
  valid: { label: "Valid", cls: "badge-bullish", help: "Market data is flowing from Upstox." },
  invalid: { label: "Rejected", cls: "badge-bearish", help: "Upstox rejected the token — generate a new analytics token in the Upstox developer console and update UPSTOX_ANALYTICS_TOKEN in backend/.env." },
  not_configured: { label: "Missing", cls: "badge-bearish", help: "Set UPSTOX_ANALYTICS_TOKEN in backend/.env and restart the backend." },
  error: { label: "Error", cls: "badge-bearish", help: "Upstox could not be reached. Check network connectivity." },
};

export default function SettingsView() {
  const { settings, updateSettings, user, isAuthenticated, logout, toast } = useAppStore();
  const navigate = useNavigateTab();
  // This view only renders client-side (tabs are chosen after hydration), so window is available
  const [notifPermission, setNotifPermission] = useState<string>(() =>
    typeof window !== "undefined" && "Notification" in window ? Notification.permission : "unsupported"
  );

  const system = useApi(() => healthAPI.system(), [isAuthenticated]);
  const ready = useApi(() => healthAPI.ready(), []);

  const toggleNotifications = async () => {
    if (settings.browserNotifications) {
      updateSettings({ browserNotifications: false });
      return toast("Browser notifications turned off", "info");
    }
    if (!("Notification" in window)) return toast("This browser does not support notifications.", "error");
    const permission = await Notification.requestPermission();
    setNotifPermission(permission);
    if (permission === "granted") {
      updateSettings({ browserNotifications: true });
      new Notification("StockMind AI", { body: "Browser notifications enabled for triggered alerts." });
      toast("Browser notifications enabled", "success");
    } else {
      toast("Notification permission was denied in the browser.", "error");
    }
  };

  const token = TOKEN_STATUS[system.data?.analytics_token] || null;
  const checks = ready.data?.checks || {};

  return (
    <div className="space-y-5">
      <PageHeader title="Settings" subtitle="Account, data connections, risk framework and display preferences" />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Account */}
        <Card>
          <SectionHeader icon={<User size={16} />} title="Account" />
          {isAuthenticated && user ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <KeyValue label="Name" value={user.full_name || "—"} />
                <KeyValue label="Email" value={<span className="break-all">{user.email}</span>} />
              </div>
              <button className="btn-secondary text-xs" onClick={() => { logout(); toast("Signed out", "info"); }}>
                <LogOut size={13} /> Sign out
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
                You&apos;re browsing as a guest. Market data, scanner, signals and analysis all work without an account.
                Sign in to save alerts and connect your Upstox portfolio.
              </p>
              <div className="flex gap-2">
                <Link href="/login?next=%2F%23settings" className="btn-primary text-xs">Sign in</Link>
                <Link href="/login?mode=register&next=%2F%23settings" className="btn-secondary text-xs">Create account</Link>
              </div>
            </div>
          )}
        </Card>

        {/* Upstox */}
        <Card>
          <SectionHeader icon={<KeyRound size={16} />} title="Upstox connection" />
          {system.loading ? (
            <LoadingRows rows={3} />
          ) : system.error ? (
            <p className="text-xs" style={{ color: "var(--color-bearish)" }}>{system.error}</p>
          ) : (
            <div className="space-y-3 text-xs">
              <div className="flex items-center justify-between">
                <span style={{ color: "var(--text-secondary)" }}>Analytics token (market data)</span>
                {token && <span className={`badge ${token.cls}`}>{token.label}</span>}
              </div>
              {token && <p style={{ color: "var(--text-muted)" }}>{token.help}</p>}
              <div className="flex items-center justify-between pt-2">
                <span style={{ color: "var(--text-secondary)" }}>OAuth app (personal portfolio)</span>
                <span className={`badge ${system.data?.oauth_configured ? "badge-bullish" : "badge-neutral"}`}>
                  {system.data?.oauth_configured ? "Configured" : "Not configured"}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span style={{ color: "var(--text-secondary)" }}>Your Upstox account</span>
                <span className={`badge ${system.data?.user_upstox_connected ? "badge-bullish" : "badge-neutral"}`}>
                  {system.data?.user_upstox_connected ? "Connected" : "Not connected"}
                </span>
              </div>
              <button className="btn-secondary text-xs mt-1" onClick={() => navigate("portfolio")}>Manage portfolio connection</button>
            </div>
          )}
        </Card>

        {/* Risk */}
        <Card>
          <SectionHeader icon={<ShieldCheck size={16} />} title="Portfolio & risk" subtitle="Used for position sizing and capital deployment" />
          <RiskForm key={`${settings.capital}:${settings.riskPct}`} />
        </Card>

        {/* Display & notifications */}
        <Card>
          <SectionHeader icon={<SlidersHorizontal size={16} />} title="Display & notifications" />
          <div className="space-y-4">
            <div>
              <label className="field-label" htmlFor="set-refresh">Auto-refresh live data</label>
              <select
                id="set-refresh"
                className="input"
                value={settings.refreshSec}
                onChange={(e) => {
                  updateSettings({ refreshSec: Number(e.target.value) });
                  toast("Refresh interval updated", "success");
                }}
              >
                <option value={30}>Every 30 seconds</option>
                <option value={60}>Every minute</option>
                <option value={300}>Every 5 minutes</option>
                <option value={0}>Off (manual refresh)</option>
              </select>
            </div>
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold flex items-center gap-1.5" style={{ color: "var(--text-primary)" }}><Bell size={13} /> Browser notifications</p>
                <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                  {notifPermission === "denied"
                    ? "Blocked in browser settings — allow notifications for this site to enable."
                    : notifPermission === "unsupported"
                    ? "Not supported by this browser."
                    : "Show a desktop notification when an alert triggers."}
                </p>
              </div>
              <button
                className={settings.browserNotifications ? "btn-secondary text-xs" : "btn-primary text-xs"}
                onClick={toggleNotifications}
                disabled={notifPermission === "denied" || notifPermission === "unsupported"}
              >
                {settings.browserNotifications ? "Turn off" : "Enable"}
              </button>
            </div>
          </div>
        </Card>

        {/* System */}
        <Card className="lg:col-span-2">
          <SectionHeader icon={<Server size={16} />} title="System status" subtitle={`Backend: ${API_BASE_URL}`} />
          {ready.loading ? (
            <LoadingRows rows={2} />
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
              {[
                // /ready reports "degraded" when only the optional Redis cache is down
                ["API", ready.error ? "offline" : checks.database === "connected" ? "online" : ready.data?.status || "unknown"],
                ["Database", checks.database],
                ["Redis cache", checks.redis?.startsWith("error") ? "not running (optional)" : checks.redis],
                ["Environment", system.data?.environment],
              ].map(([k, v]) => (
                <div key={k} className="flex items-center gap-2">
                  <Database size={13} style={{ color: "var(--text-muted)" }} />
                  <span style={{ color: "var(--text-muted)" }}>{k}:</span>
                  <span style={{ color: "var(--text-primary)" }}>{v || "—"}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

function RiskForm() {
  const { settings, updateSettings, toast } = useAppStore();
  const [capital, setCapital] = useState(String(settings.capital));
  const [riskPct, setRiskPct] = useState(String(settings.riskPct));

  const saveRisk = (e: React.FormEvent) => {
    e.preventDefault();
    const c = parseFloat(capital);
    const r = parseFloat(riskPct);
    if (!(c >= 10000)) return toast("Capital must be at least ₹10,000.", "error");
    if (!(r > 0 && r <= 5)) return toast("Risk per trade must be between 0 and 5%.", "error");
    updateSettings({ capital: c, riskPct: r });
    toast("Risk settings saved — signals and position sizes will update.", "success");
  };

  return (
    <form onSubmit={saveRisk} className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="field-label" htmlFor="set-capital">Capital (₹)</label>
          <input id="set-capital" className="input" type="number" min={10000} step={1000} value={capital} onChange={(e) => setCapital(e.target.value)} />
        </div>
        <div>
          <label className="field-label" htmlFor="set-risk">Risk per trade (%)</label>
          <input id="set-risk" className="input" type="number" min={0.1} max={5} step={0.05} value={riskPct} onChange={(e) => setRiskPct(e.target.value)} />
        </div>
      </div>
      <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
        Max loss per trade: {fmtINR(((parseFloat(capital) || 0) * (parseFloat(riskPct) || 0)) / 100, 0)}. High-conviction setups size at 1.33× and low-quality at 0.67× of this.
      </p>
      <div className="flex gap-2">
        <button type="submit" className="btn-primary text-xs"><Save size={13} /> Save</button>
        <button
          type="button"
          className="btn-ghost text-xs"
          onClick={() => {
            updateSettings({ capital: DEFAULT_SETTINGS.capital, riskPct: DEFAULT_SETTINGS.riskPct });
            toast("Risk settings reset to defaults", "info");
          }}
        >
          Reset to defaults
        </button>
      </div>
    </form>
  );
}
