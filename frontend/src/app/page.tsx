"use client";

import { useEffect } from "react";
import AppShell from "@/components/AppShell";
import AlertsView from "@/components/views/AlertsView";
import AnalyticsView from "@/components/views/AnalyticsView";
import DashboardView from "@/components/views/DashboardView";
import NewsView from "@/components/views/NewsView";
import PortfolioView from "@/components/views/PortfolioView";
import PredictionsView from "@/components/views/PredictionsView";
import PromptView from "@/components/views/PromptView";
import ReportView from "@/components/views/ReportView";
import ScannerView from "@/components/views/ScannerView";
import SectorsView from "@/components/views/SectorsView";
import SettingsView from "@/components/views/SettingsView";
import SignalsView from "@/components/views/SignalsView";
import USStockView from "@/components/views/USStockView";
import { Tab, TABS, useAppStore } from "@/lib/store";

const VIEWS: Record<Tab, () => React.JSX.Element> = {
  dashboard: DashboardView,
  scanner: ScannerView,
  predictions: PredictionsView,
  portfolio: PortfolioView,
  signals: SignalsView,
  analytics: AnalyticsView,
  sectors: SectorsView,
  news: NewsView,
  alerts: AlertsView,
  prompt: PromptView,
  report: ReportView,
  us_stocks: USStockView,
  settings: SettingsView,
};

const TITLES: Record<Tab, string> = {
  dashboard: "Dashboard",
  scanner: "Market Scanner",
  predictions: "Predictions",
  portfolio: "Portfolio",
  signals: "Daily Signals",
  analytics: "Analytics",
  sectors: "Sector Map",
  news: "News & Events",
  alerts: "Alerts",
  prompt: "AI Prompt",
  report: "Stock Report",
  us_stocks: "US Stocks",
  settings: "Settings",
};

function tabFromHash(): Tab {
  const hash = window.location.hash.replace("#", "") as Tab;
  return TABS.includes(hash) ? hash : "dashboard";
}

export default function HomePage() {
  const { activeTab, setActiveTab, toast } = useAppStore();

  // Keep the active view in sync with the URL hash (deep links + back/forward)
  useEffect(() => {
    const sync = () => setActiveTab(tabFromHash());
    sync();
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, [setActiveTab]);

  // Result of the Upstox OAuth redirect (?upstox=connected|error)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const result = params.get("upstox");
    if (!result) return;
    if (result === "connected") toast("Upstox account connected", "success");
    else toast(`Upstox connection failed: ${params.get("message") || "unknown error"}`, "error");
    window.history.replaceState(null, "", window.location.pathname + window.location.hash);
  }, [toast]);

  useEffect(() => {
    document.title = `${TITLES[activeTab]} · StockMind AI`;
    window.scrollTo({ top: 0 });
  }, [activeTab]);

  const View = VIEWS[activeTab];
  return (
    <AppShell>
      <div key={activeTab} className="animate-fade-in">
        <View />
      </div>
    </AppShell>
  );
}
