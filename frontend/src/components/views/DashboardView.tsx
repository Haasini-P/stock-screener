"use client";

import { useState } from "react";
import {
  Activity,
  BarChart3,
  Brain,
  ChevronRight,
  Clock,
  DollarSign,
  FileSearch,
  Globe,
  LineChart as LineChartIcon,
  Newspaper,
  Search,
  Shield,
  Sparkles,
  Target,
  TrendingDown,
  TrendingUp,
  Wallet,
  Zap,
} from "lucide-react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { aiAPI, marketAPI, paperTradingAPI, signalsAPI, usMarketAPI, watchlistAPI } from "@/lib/api";
import { portfolioParams, useAppStore } from "@/lib/store";
import { useApi } from "@/lib/useApi";
import { fmtDate, fmtINR, fmtNum, fmtPct, fmtTime, fmtUSD, timeAgo, toneColor } from "@/lib/format";
import { useNavigateTab } from "../AppShell";
import SearchBox from "../SearchBox";
import { BucketChips, Card, Change, EmptyState, EntryBadge, ErrorState, InitialsBadge, LoadingRows, SectionHeader, Skeleton, StockLink } from "../ui";

export const SECTOR_ICONS: Record<string, { icon: typeof Shield; color: string }> = {
  Defence: { icon: Shield, color: "#ef4444" },
  "Power & Grid": { icon: Zap, color: "#f59e0b" },
  Semiconductor: { icon: Activity, color: "#6366f1" },
  "AI / Data Centre": { icon: Brain, color: "#22d3ee" },
  "Pharma / CDMO": { icon: Sparkles, color: "#22c55e" },
  "Cables & Wires": { icon: LineChartIcon, color: "#a855f7" },
  "EV / Electronics": { icon: BarChart3, color: "#ec4899" },
  Chemicals: { icon: Globe, color: "#14b8a6" },
};

// Still used by AnalyticsView.tsx/SignalsView.tsx even though this page no
// longer shows a standalone regime banner (the ticker strip replaces it).
export const regimeColor = (regime?: string) => {
  const r = (regime || "").toLowerCase();
  if (r.includes("risk-on") || r.includes("bull")) return "var(--color-bullish)";
  if (r.includes("risk-off") || r.includes("bear")) return "var(--color-bearish)";
  return "var(--color-neutral)";
};

const US_ACCENT = "#2563eb"; // same accent used on the US Stocks page
const INDIA_ACCENT = "#6366f1"; // this app's existing indigo accent
const RANGES = ["1W", "1M", "3M", "1Y"] as const;

const US_CHIPS = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META"];
const INDIA_CHIPS = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "TATASTEEL", "LT", "SBIN"];

// ---------- Ticker strip ----------

function Sparkline({ points, color }: { points: { t: string; value: number }[]; color: string }) {
  if (!points.length) return <div className="w-16 h-8" />;
  return (
    <div className="w-16 h-8">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points}>
          <Line type="monotone" dataKey="value" stroke={color} strokeWidth={1.5} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function TickerStrip() {
  const usLatest = useApi(() => usMarketAPI.indicesLatest(), [], { refreshMs: 60000 });
  const usHistory = useApi(() => usMarketAPI.indicesHistory("1W"), []);
  const inLatest = useApi(() => marketAPI.indicesLatest(), [], { refreshMs: 60000 });
  const inHistory = useApi(() => marketAPI.indicesHistory("1W"), []);

  const loading = usLatest.loading || inLatest.loading;
  if (loading) return <Card><LoadingRows rows={1} /></Card>;

  const usIndices: any[] = usLatest.data?.indices || [];
  const usSeries: any[] = usHistory.data?.series || [];
  const inIndices: any[] = inLatest.data?.indices || [];
  const inSeries: any[] = inHistory.data?.series || [];

  const row = (idx: any, points: { t: string; value: number }[], fmtPrice: (v: number) => string) => (
    <div key={idx.name} className="flex items-center gap-2 shrink-0">
      <div>
        <p className="text-xs font-semibold" style={{ color: "var(--text-primary)" }}>{idx.name}</p>
        <p className="text-sm font-bold tabular-nums" style={{ color: "var(--text-primary)" }}>{fmtPrice(idx.price)}</p>
        {idx.change_pct != null && (
          <p className={`text-[11px] font-semibold ${idx.change_pct >= 0 ? "text-bullish" : "text-bearish"}`}>{fmtPct(idx.change_pct)}</p>
        )}
      </div>
      <Sparkline points={points} color={idx.change_pct >= 0 ? "#22c55e" : "#ef4444"} />
    </div>
  );

  return (
    <Card>
      <div className="flex flex-wrap items-center gap-6 overflow-x-auto">
        {usIndices.map((idx) => row(idx, usSeries.find((s: any) => s.name === idx.name)?.points || [], fmtUSD))}
        {(usIndices.length > 0 && inIndices.length > 0) && <div className="w-px h-10 shrink-0" style={{ background: "var(--border-subtle)" }} />}
        {inIndices.map((idx) => row(idx, inSeries.find((s: any) => s.name === idx.name)?.points || [], (v) => fmtINR(v, 0)))}
        {usIndices.length === 0 && inIndices.length === 0 && (
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>Index data unavailable right now.</p>
        )}
      </div>
    </Card>
  );
}

// ---------- Hero cards ----------

function HeroCard({
  accent, flag, title, subtitle, chips, onChipClick, moreHref, tiles,
}: {
  accent: string;
  flag: string;
  title: string;
  subtitle: string;
  chips: string[];
  onChipClick: (symbol: string) => void;
  moreHref: () => void;
  tiles: { icon: React.ReactNode; label: string; description: string; onClick: () => void }[];
}) {
  return (
    <div className="glass-card-static overflow-hidden">
      <div
        className="p-5 relative"
        style={{ background: `linear-gradient(135deg, ${accent}30, ${accent}08)`, borderBottom: `1px solid ${accent}30` }}
      >
        <button className="absolute top-4 right-4 w-8 h-8 rounded-full flex items-center justify-center" style={{ background: `${accent}25`, color: accent }} onClick={moreHref} title={`Open ${title}`}>
          <ChevronRight size={16} />
        </button>
        <div className="flex items-center gap-3">
          <span className="text-3xl leading-none">{flag}</span>
          <div>
            <h3 className="text-lg font-bold" style={{ color: "var(--text-primary)" }}>{title}</h3>
            <p className="text-xs" style={{ color: "var(--text-secondary)" }}>{subtitle}</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2 mt-4">
          {chips.map((sym) => (
            <button key={sym} className="chip" style={{ borderColor: `${accent}40` }} onClick={() => onChipClick(sym)}>{sym}</button>
          ))}
          <button className="chip" onClick={moreHref}>···</button>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-px" style={{ background: "var(--border-subtle)" }}>
        {tiles.map((tile) => (
          <button key={tile.label} className="p-3 text-left flex flex-col gap-1" style={{ background: "var(--bg-secondary)" }} onClick={tile.onClick}>
            <span style={{ color: accent }}>{tile.icon}</span>
            <span className="text-xs font-semibold" style={{ color: "var(--text-primary)" }}>{tile.label}</span>
            <span className="text-[10px]" style={{ color: "var(--text-muted)" }}>{tile.description}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

// ---------- Market overview chart ----------

const CHART_TOOLTIP = {
  contentStyle: { background: "var(--bg-card)", border: "1px solid var(--border-subtle)", borderRadius: 8, fontSize: 11 },
  labelStyle: { color: "var(--text-muted)" },
};

function MarketOverviewChart({
  accent, title, fetchHistory, lineColors,
}: {
  accent: string;
  title: string;
  fetchHistory: (range: string) => Promise<{ data: { data_available: boolean; series: { name: string; points: { t: string; value: number }[] }[] } }>;
  lineColors: string[];
}) {
  const [range, setRange] = useState<(typeof RANGES)[number]>("1M");
  const history = useApi(() => fetchHistory(range), [range]);

  const series = history.data?.series || [];
  // Merge per-line point arrays into one array of {t, [name]: value} rows for recharts
  const merged: Record<string, any> = {};
  series.forEach((s) => {
    s.points.forEach((p) => {
      const key = p.t.slice(0, 10);
      merged[key] = merged[key] || { t: key };
      merged[key][s.name] = p.value;
    });
  });
  const rows = Object.values(merged).sort((a: any, b: any) => (a.t > b.t ? 1 : -1));

  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <SectionHeader title={title} subtitle="% change over range" />
        <div className="flex gap-1">
          {RANGES.map((r) => (
            <button key={r} className={`chip ${range === r ? "chip-active" : ""}`} onClick={() => setRange(r)}>{r}</button>
          ))}
        </div>
      </div>
      {history.loading ? (
        <Skeleton className="h-56 w-full" />
      ) : history.error ? (
        <ErrorState message={history.error} onRetry={history.reload} />
      ) : !history.data?.data_available || rows.length === 0 ? (
        <EmptyState icon={<LineChartIcon size={24} />} title="Chart data unavailable" description="Needs a configured data source — see Settings." />
      ) : (
        <>
          <div style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={rows}>
                <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
                <XAxis dataKey="t" tick={{ fill: "#565d73", fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "#565d73", fontSize: 10 }} axisLine={false} tickLine={false} width={44} tickFormatter={(v) => `${v}%`} />
                <Tooltip {...CHART_TOOLTIP} formatter={(v: any) => `${v}%`} />
                {series.map((s, i) => (
                  <Line key={s.name} type="monotone" dataKey={s.name} stroke={lineColors[i % lineColors.length]} strokeWidth={2} dot={false} isAnimationActive={false} />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="flex flex-wrap gap-4 mt-2">
            {series.map((s, i) => (
              <span key={s.name} className="text-[11px] flex items-center gap-1.5" style={{ color: "var(--text-secondary)" }}>
                <span className="w-2 h-2 rounded-full" style={{ background: lineColors[i % lineColors.length] }} />
                {s.name}
              </span>
            ))}
          </div>
        </>
      )}
    </Card>
  );
}

// ---------- Movers panel (Gainers / Losers / Most Active tabs) ----------

function MoversPanel({
  accent, title, data, loading, error, onRetry, fmtPrice, navigate,
}: {
  accent: string;
  title: string;
  data: { gainers?: any[]; losers?: any[]; most_active?: any[]; volume_shockers?: any[]; data_available?: boolean; reason?: string } | null | undefined;
  loading: boolean;
  error: string;
  onRetry: () => void;
  fmtPrice: (v: number) => string;
  navigate: () => void;
}) {
  const [tab, setTab] = useState<"gainers" | "losers" | "active">("gainers");
  const rows = tab === "gainers" ? data?.gainers : tab === "losers" ? data?.losers : (data?.most_active || data?.volume_shockers);

  return (
    <Card padded={false}>
      <div className="px-5 py-4 flex items-center justify-between border-b" style={{ borderColor: "var(--border-subtle)" }}>
        <h3 className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>{title}</h3>
        <button className="btn-ghost text-xs" onClick={navigate}>More <ChevronRight size={14} /></button>
      </div>
      <div className="flex gap-1 px-4 pt-3">
        {([["gainers", "Gainers"], ["losers", "Losers"], ["active", "Most Active"]] as const).map(([key, label]) => (
          <button key={key} className={`chip ${tab === key ? "chip-active" : ""}`} onClick={() => setTab(key)}>{label}</button>
        ))}
      </div>
      <div className="p-4 space-y-1">
        {loading ? (
          [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-8 w-full" />)
        ) : error ? (
          <ErrorState message={error} onRetry={onRetry} />
        ) : data?.data_available === false ? (
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>{data.reason || "Not available."}</p>
        ) : !rows?.length ? (
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>No data.</p>
        ) : (
          rows.slice(0, 5).map((m: any) => (
            <div key={m.symbol} className="flex items-center gap-2.5 text-xs py-1.5">
              <InitialsBadge symbol={m.symbol} size={28} />
              <div className="min-w-0 flex-1">
                <StockLink symbol={m.symbol} />
                <p className="text-[10px] truncate" style={{ color: "var(--text-muted)" }}>{m.sector || m.name}</p>
              </div>
              <div className="text-right shrink-0">
                <p className="tabular-nums font-semibold" style={{ color: "var(--text-primary)" }}>{fmtPrice(m.ltp)}</p>
                <Change value={m.change_pct} className="text-[10px] justify-end" />
              </div>
            </div>
          ))
        )}
      </div>
    </Card>
  );
}

// ---------- Recent analysis panel ----------

function RecentAnalysisPanel({
  title, items, loading, error, onRetry, onOpen,
}: {
  title: string;
  items: { symbol: string; model: string; generated_at: string }[] | undefined;
  loading: boolean;
  error: string;
  onRetry: () => void;
  onOpen: (symbol: string) => void;
}) {
  return (
    <Card padded={false}>
      <div className="px-5 py-4 border-b" style={{ borderColor: "var(--border-subtle)" }}>
        <h3 className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>{title}</h3>
      </div>
      <div className="p-4 space-y-1">
        {loading ? (
          [0, 1, 2].map((i) => <Skeleton key={i} className="h-9 w-full" />)
        ) : error ? (
          <ErrorState message={error} onRetry={onRetry} />
        ) : !items?.length ? (
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>No AI analysis generated yet.</p>
        ) : (
          items.map((item) => (
            <button key={item.symbol} className="flex items-center gap-2.5 text-xs py-1.5 w-full text-left hover:bg-white/[0.02] rounded-lg px-1" onClick={() => onOpen(item.symbol)}>
              <InitialsBadge symbol={item.symbol} size={28} />
              <div className="min-w-0 flex-1">
                <p className="font-semibold" style={{ color: "var(--text-primary)" }}>{item.symbol}</p>
                <p className="text-[10px]" style={{ color: "var(--text-muted)" }}>AI Analysis Report</p>
              </div>
              <span className="text-[10px] shrink-0" style={{ color: "var(--text-muted)" }}>{timeAgo(item.generated_at)}</span>
            </button>
          ))
        )}
      </div>
    </Card>
  );
}

// ---------- Main dashboard ----------

export default function DashboardView() {
  const { settings, setSelectedSector, setReportSymbol, setUsSymbol, isAuthenticated } = useAppStore();
  const navigate = useNavigateTab();
  const refreshMs = settings.refreshSec * 1000;

  const movers = useApi(() => marketAPI.movers(5), [], { refreshMs: refreshMs ? Math.max(refreshMs, 60000) : 0 });
  const usMovers = useApi(() => usMarketAPI.movers(), [], { refreshMs: refreshMs ? Math.max(refreshMs, 60000) : 0 });
  const sectors = useApi(() => marketAPI.sectors(), [], { refreshMs: refreshMs ? Math.max(refreshMs, 60000) : 0 });
  const daily = useApi(() => signalsAPI.dailyList(portfolioParams(settings)), [settings.capital, settings.riskPct]);
  const watchlist = useApi(() => watchlistAPI.list(), [], { refreshMs: refreshMs ? Math.max(refreshMs, 60000) : 0 });
  const usSummary = useApi(() => paperTradingAPI.summary(), [], { enabled: isAuthenticated });
  const recentIndia = useApi(() => aiAPI.recentCommentary(5), []);
  const recentUS = useApi(() => usMarketAPI.recentResearch(5), []);

  const openReport = (symbol: string) => {
    setReportSymbol(symbol);
    navigate("report");
  };
  const openUsStock = (symbol: string) => {
    setUsSymbol(symbol);
    navigate("us_stocks");
  };

  const topPicks = daily.data
    ? [...daily.data.top_picks.short_term, ...daily.data.top_picks.mid_term, ...daily.data.top_picks.long_term]
        .sort((a: any, b: any) => b.score - a.score)
        .slice(0, 6)
    : [];
  const sectorMap: Record<string, any> = Object.fromEntries((sectors.data?.sectors || []).map((s: any) => [s.sector, s]));
  const suggested = [...(watchlist.data?.items || [])]
    .sort((a: any, b: any) => new Date(b.added_at).getTime() - new Date(a.added_at).getTime())
    .slice(0, 8);

  return (
    <div className="space-y-5">
      {/* Ticker strip */}
      <TickerStrip />

      {/* Hero cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <HeroCard
          accent={US_ACCENT}
          flag="🇺🇸"
          title="US Stocks"
          subtitle="NYSE & NASDAQ Analysis"
          chips={US_CHIPS}
          onChipClick={openUsStock}
          moreHref={() => navigate("us_stocks")}
          tiles={[
            { icon: <Brain size={16} />, label: "AI Stock Analysis", description: "Fundamentals, technicals, news, SEC filings", onClick: () => navigate("us_stocks") },
            { icon: <Search size={16} />, label: "US Stock Scanner", description: "Find favorable setups automatically", onClick: () => navigate("us_stocks") },
            { icon: <Sparkles size={16} />, label: "Paper Trading", description: "Practice trades with real signals", onClick: () => navigate("us_stocks") },
            { icon: <Newspaper size={16} />, label: "US Market Insights", description: "Indices, sectors, news & events", onClick: () => navigate("us_stocks") },
          ]}
        />
        <HeroCard
          accent={INDIA_ACCENT}
          flag="🇮🇳"
          title="Indian Stocks"
          subtitle="NSE & BSE Analysis"
          chips={INDIA_CHIPS}
          onChipClick={openReport}
          moreHref={() => navigate("report")}
          tiles={[
            { icon: <Brain size={16} />, label: "AI Stock Analysis", description: "Fundamentals, technicals, news, earnings", onClick: () => navigate("report") },
            { icon: <Search size={16} />, label: "India Stock Scanner", description: "Smallcap & midcap opportunities", onClick: () => navigate("scanner") },
            { icon: <Target size={16} />, label: "Watchlist", description: "Track & manage your stocks", onClick: () => navigate("scanner") },
            { icon: <Newspaper size={16} />, label: "Market Insights", description: "Indices, sectors, news & events", onClick: () => navigate("analytics") },
          ]}
        />
      </div>

      {/* Market overview charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <MarketOverviewChart accent={US_ACCENT} title="US Market Overview" fetchHistory={usMarketAPI.indicesHistory} lineColors={["#2563eb", "#a855f7", "#22c55e"]} />
        <MarketOverviewChart accent={INDIA_ACCENT} title="Indian Market Overview" fetchHistory={marketAPI.indicesHistory} lineColors={["#f59e0b", "#ef4444", "#22c55e"]} />
      </div>

      {/* Movers + Recent analysis */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <MoversPanel accent={US_ACCENT} title="Top US Movers" data={usMovers.data} loading={usMovers.loading} error={usMovers.error} onRetry={usMovers.reload} fmtPrice={fmtUSD} navigate={() => navigate("us_stocks")} />
        <RecentAnalysisPanel title="Recent US Analysis" items={recentUS.data?.items} loading={recentUS.loading} error={recentUS.error} onRetry={recentUS.reload} onOpen={openUsStock} />
        <MoversPanel accent={INDIA_ACCENT} title="Top Indian Movers" data={movers.data} loading={movers.loading} error={movers.error} onRetry={movers.reload} fmtPrice={(v) => fmtINR(v)} navigate={() => navigate("scanner")} />
        <RecentAnalysisPanel title="Recent Indian Analysis" items={recentIndia.data?.items} loading={recentIndia.loading} error={recentIndia.error} onRetry={recentIndia.reload} onOpen={openReport} />
      </div>

      {/* Manual stock entry — full analysis for any symbol, not just scanner picks */}
      <Card className="flex flex-col sm:flex-row sm:items-center gap-3">
        <div className="flex items-center gap-2 shrink-0">
          <FileSearch size={16} style={{ color: "var(--accent-indigo)" }} />
          <p className="text-sm font-bold whitespace-nowrap" style={{ color: "var(--text-primary)" }}>Analyze a stock</p>
        </div>
        <SearchBox
          className="w-full sm:max-w-md"
          placeholder="Enter any NSE stock symbol for a full report (e.g. RELIANCE)…"
          onSelect={openReport}
        />
        <p className="text-[11px] sm:ml-auto" style={{ color: "var(--text-muted)" }}>
          Opens the full Stock Report — thesis, trade plan, term outlook, fundamentals and news.
        </p>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Daily Stock Signals */}
        <div className="lg:col-span-2 glass-card-static overflow-hidden">
          <div className="px-5 py-4 flex items-center justify-between border-b" style={{ borderColor: "var(--border-subtle)" }}>
            <div className="flex items-center gap-2">
              <Zap size={16} style={{ color: "var(--accent-indigo)" }} />
              <h3 className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>Daily Stock Signals</h3>
              <span className="badge badge-info">Live</span>
            </div>
            <button className="btn-ghost text-xs" onClick={() => navigate("signals")}>View All <ChevronRight size={14} /></button>
          </div>
          <div className="p-5">
            {daily.loading ? (
              <div className="space-y-3">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-9 w-full" />)}</div>
            ) : daily.error ? (
              <ErrorState message={daily.error} onRetry={daily.reload} />
            ) : topPicks.length === 0 ? (
              <EmptyState
                icon={<Sparkles size={28} />}
                title="No qualifying setups right now"
                description={`Regime is ${daily.data?.market_regime?.regime}. The discovery engine found no stocks meeting entry rules — cash is a valid position.`}
                action={<button className="btn-secondary text-xs" onClick={() => navigate("scanner")}>Open scanner</button>}
              />
            ) : (
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr><th>Stock</th><th>Entry</th><th>CMP</th><th>Stop</th><th>Target</th><th>P(up)</th><th>Horizon</th></tr>
                  </thead>
                  <tbody>
                    {topPicks.map((s: any) => (
                      <tr key={s.symbol}>
                        <td><StockLink symbol={s.symbol} /><div className="text-[10px]" style={{ color: "var(--text-muted)" }}>{s.sector}</div></td>
                        <td><EntryBadge entry={s.entry} /></td>
                        <td className="tabular-nums">{fmtINR(s.ltp)} <Change value={s.change_pct} className="text-[10px]" /></td>
                        <td className="tabular-nums">{fmtINR(s.stop_loss)}</td>
                        <td className="tabular-nums">{fmtINR(s.target_1)}</td>
                        <td className="tabular-nums">{s.probability_up != null ? `${(s.probability_up * 100).toFixed(0)}%` : "—"}</td>
                        <td className="text-xs">{s.horizon?.replace("_", " ")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Portfolio & US Paper Trading quick-cards */}
        <div className="space-y-5">
          <button className="glass-card p-5 w-full text-left" onClick={() => navigate("portfolio")}>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Wallet size={16} style={{ color: "var(--accent-indigo)" }} />
                <h3 className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>Portfolio</h3>
              </div>
              <ChevronRight size={14} style={{ color: "var(--text-muted)" }} />
            </div>
            <p className="text-lg font-bold" style={{ color: "var(--text-primary)" }}>{fmtINR(settings.capital, 0)}</p>
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>Configured capital</p>
            <div className="flex gap-6 mt-3 text-xs" style={{ color: "var(--text-muted)" }}>
              <div><p className="font-semibold" style={{ color: "var(--text-primary)" }}>{settings.riskPct}%</p><p>Risk / trade</p></div>
              <div><p className="font-semibold" style={{ color: "var(--text-primary)" }}>{fmtINR(settings.capital * settings.riskPct / 100, 0)}</p><p>Max loss / trade</p></div>
              {daily.data && (
                <div><p className="font-semibold" style={{ color: "var(--text-primary)" }}>{daily.data.capital_deployment.suggested_deployment_pct}%</p><p>Deploy now</p></div>
              )}
            </div>
          </button>

          <button className="glass-card p-5 w-full text-left" onClick={() => navigate("us_stocks")}>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <DollarSign size={16} style={{ color: US_ACCENT }} />
                <h3 className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>US Paper Trading</h3>
              </div>
              <ChevronRight size={14} style={{ color: "var(--text-muted)" }} />
            </div>
            {!isAuthenticated ? (
              <p className="text-xs" style={{ color: "var(--text-muted)" }}>Sign in to track simulated US stock trades and estimated tax.</p>
            ) : usSummary.loading ? (
              <Skeleton className="h-8 w-32" />
            ) : usSummary.error ? (
              <p className="text-xs" style={{ color: "var(--text-muted)" }}>No paper trading activity yet.</p>
            ) : usSummary.data ? (
              <>
                <p
                  className="text-lg font-bold tabular-nums"
                  style={{ color: usSummary.data.net_after_tax >= 0 ? "var(--color-bullish)" : "var(--color-bearish)" }}
                >
                  {fmtUSD(usSummary.data.net_after_tax)}
                </p>
                <p className="text-xs" style={{ color: "var(--text-muted)" }}>Net after estimated tax</p>
                <div className="flex gap-6 mt-3 text-xs" style={{ color: "var(--text-muted)" }}>
                  <div><p className="font-semibold" style={{ color: "var(--text-primary)" }}>{fmtUSD(usSummary.data.total_realized_gain)}</p><p>Realized gain</p></div>
                  <div><p className="font-semibold" style={{ color: "var(--text-primary)" }}>{fmtUSD(usSummary.data.total_estimated_tax)}</p><p>Est. tax</p></div>
                  <div><p className="font-semibold" style={{ color: "var(--text-primary)" }}>{usSummary.data.open_positions_count}</p><p>Open positions</p></div>
                </div>
              </>
            ) : null}
          </button>
        </div>
      </div>

      {/* Suggested stocks — scanner watchlist, with when each one was first flagged */}
      <div className="glass-card-static overflow-hidden">
        <div className="px-5 py-4 flex items-center justify-between border-b" style={{ borderColor: "var(--border-subtle)" }}>
          <div className="flex items-center gap-2">
            <Clock size={16} style={{ color: "var(--accent-indigo)" }} />
            <h3 className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>Recently Suggested Stocks</h3>
          </div>
          <button className="btn-ghost text-xs" onClick={() => navigate("scanner")}>Open Scanner <ChevronRight size={14} /></button>
        </div>
        <div className="p-5">
          {watchlist.loading ? (
            <div className="space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-9 w-full" />)}</div>
          ) : watchlist.error ? (
            <ErrorState message={watchlist.error} onRetry={watchlist.reload} />
          ) : suggested.length === 0 ? (
            <EmptyState
              icon={<Sparkles size={28} />}
              title="No suggested stocks yet"
              description="Stocks get tracked here automatically once the Market Scanner flags them, with the date and time they were first suggested."
              action={<button className="btn-secondary text-xs" onClick={() => navigate("scanner")}>Open scanner</button>}
            />
          ) : (
            <div className="table-scroll">
              <table className="data-table">
                <thead><tr><th>Stock</th><th>Setup</th><th>Term</th><th>Source</th><th>Suggested on</th></tr></thead>
                <tbody>
                  {suggested.map((item: any) => (
                    <tr key={item.symbol} className="cursor-pointer" onClick={() => openReport(item.symbol)}>
                      <td><StockLink symbol={item.symbol} /></td>
                      <td><BucketChips buckets={item.bucket ? [item.bucket] : undefined} /></td>
                      <td><span className="badge badge-neutral">{item.term}</span></td>
                      <td className="text-xs" style={{ color: "var(--text-muted)" }}>{item.source === "manual" ? "Manually added" : "Scanner"}</td>
                      <td className="text-xs whitespace-nowrap" style={{ color: "var(--text-secondary)" }}>{fmtDate(item.added_at)} · {fmtTime(item.added_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Sector grid */}
      <div className="glass-card-static overflow-hidden">
        <div className="px-5 py-4 border-b flex items-center justify-between" style={{ borderColor: "var(--border-subtle)" }}>
          <div>
            <h3 className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>Approved Sector Universe</h3>
            <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>Stocks are screened from these high-conviction sectors only — click a sector for details</p>
          </div>
          <button className="btn-ghost text-xs" onClick={() => navigate("sectors")}>Sector Map <ChevronRight size={14} /></button>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4">
          {Object.entries(SECTOR_ICONS).map(([name, { icon: Icon, color: c }]) => {
            const s = sectorMap[name];
            return (
              <button
                key={name}
                onClick={() => {
                  setSelectedSector(name);
                  navigate("sectors");
                }}
                className="flex items-center gap-3 p-4 text-left transition-all duration-200 hover:bg-white/[0.03]"
                style={{ borderRight: "1px solid var(--border-subtle)", borderBottom: "1px solid var(--border-subtle)" }}
              >
                <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0" style={{ background: `${c}15`, color: c }}>
                  <Icon size={16} />
                </div>
                <div className="min-w-0">
                  <span className="block text-xs font-semibold truncate" style={{ color: "var(--text-secondary)" }}>{name}</span>
                  {sectors.loading ? (
                    <Skeleton className="h-3 w-12 mt-1" />
                  ) : s ? (
                    <span className="text-[11px] font-semibold tabular-nums" style={{ color: toneColor(s.change_pct) }}>
                      {fmtPct(s.change_pct)} · {s.advances}▲ {s.declines}▼
                    </span>
                  ) : null}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Disclaimer */}
      <div className="glass-card-static p-3 flex items-start gap-3" style={{ borderLeft: "3px solid var(--color-info)" }}>
        <Shield size={16} style={{ color: "var(--color-info)", flexShrink: 0, marginTop: 1 }} />
        <p className="text-[11px] leading-relaxed" style={{ color: "var(--text-muted)" }}>
          <strong style={{ color: "var(--text-secondary)" }}>ANALYTICAL DECISION-SUPPORT SYSTEM.</strong>{" "}
          Probabilistic estimates, not certainties. No trades are executed automatically. Indian data from Upstox, US data
          from Alpaca (once configured) and SEC EDGAR. Protect capital first — opportunity comes second.
        </p>
      </div>
    </div>
  );
}
