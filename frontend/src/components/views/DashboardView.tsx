"use client";

import {
  Activity,
  BarChart3,
  Brain,
  ChevronRight,
  Globe,
  LineChart,
  Shield,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Wallet,
  Zap,
} from "lucide-react";
import { marketAPI, signalsAPI } from "@/lib/api";
import { portfolioParams, useAppStore } from "@/lib/store";
import { useApi } from "@/lib/useApi";
import { fmtINR, fmtINRCompact, fmtNum, fmtPct, tone, toneColor } from "@/lib/format";
import { useNavigateTab } from "../AppShell";
import { Card, Change, EmptyState, EntryBadge, ErrorState, Skeleton, StockLink } from "../ui";

export const SECTOR_ICONS: Record<string, { icon: typeof Shield; color: string }> = {
  Defence: { icon: Shield, color: "#ef4444" },
  "Power & Grid": { icon: Zap, color: "#f59e0b" },
  Semiconductor: { icon: Activity, color: "#6366f1" },
  "AI / Data Centre": { icon: Brain, color: "#22d3ee" },
  "Pharma / CDMO": { icon: Sparkles, color: "#22c55e" },
  "Cables & Wires": { icon: LineChart, color: "#a855f7" },
  "EV / Electronics": { icon: BarChart3, color: "#ec4899" },
  Chemicals: { icon: Globe, color: "#14b8a6" },
};

export const regimeColor = (regime?: string) => {
  const r = (regime || "").toLowerCase();
  if (r.includes("risk-on") || r.includes("bull")) return "var(--color-bullish)";
  if (r.includes("risk-off") || r.includes("bear")) return "var(--color-bearish)";
  return "var(--color-neutral)";
};

function MetricCard({
  title,
  value,
  change,
  changeTone,
  subtitle,
  icon,
  onClick,
  loading,
}: {
  title: string;
  value: string;
  change?: string;
  changeTone?: "bullish" | "bearish" | "neutral";
  subtitle?: string;
  icon: React.ReactNode;
  onClick?: () => void;
  loading?: boolean;
}) {
  const color =
    changeTone === "bullish" ? "var(--color-bullish)" : changeTone === "bearish" ? "var(--color-bearish)" : "var(--color-neutral)";
  return (
    <button className="glass-card metric-card text-left w-full" onClick={onClick}>
      <div className="flex items-start justify-between mb-3">
        <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>{title}</span>
        <div className="p-1.5 rounded-md" style={{ background: "rgba(99, 102, 241, 0.1)" }}>{icon}</div>
      </div>
      {loading ? (
        <Skeleton className="h-8 w-32" />
      ) : (
        <div className="text-2xl font-bold tracking-tight tabular-nums" style={{ color: "var(--text-primary)" }}>{value}</div>
      )}
      {change && !loading && (
        <div className="flex items-center gap-1.5 mt-1.5">
          {changeTone === "bullish" ? <TrendingUp size={14} className="text-bullish" /> : changeTone === "bearish" ? <TrendingDown size={14} className="text-bearish" /> : null}
          <span className="text-sm font-semibold" style={{ color }}>{change}</span>
        </div>
      )}
      {subtitle && <p className="text-xs mt-1 truncate" style={{ color: "var(--text-muted)" }}>{subtitle}</p>}
    </button>
  );
}

export default function DashboardView() {
  const { settings, setSelectedSector } = useAppStore();
  const navigate = useNavigateTab();
  const refreshMs = settings.refreshSec * 1000;

  const regime = useApi(() => signalsAPI.regime(), [], { refreshMs });
  const movers = useApi(() => marketAPI.movers(5), [], { refreshMs: refreshMs ? Math.max(refreshMs, 60000) : 0 });
  const sectors = useApi(() => marketAPI.sectors(), [], { refreshMs: refreshMs ? Math.max(refreshMs, 60000) : 0 });
  const daily = useApi(() => signalsAPI.dailyList(portfolioParams(settings)), [settings.capital, settings.riskPct]);

  const r = regime.data;
  const idx = r?.indian_market || {};
  const breadth = movers.data?.breadth;
  const fii = r?.fii_activity;
  const color = regimeColor(r?.regime);
  const evidence: string[] = [...(r?.evidence?.regime || [])];
  const topPicks = daily.data
    ? [...daily.data.top_picks.short_term, ...daily.data.top_picks.mid_term, ...daily.data.top_picks.long_term]
        .sort((a: any, b: any) => b.score - a.score)
        .slice(0, 6)
    : [];
  const sectorMap: Record<string, any> = Object.fromEntries((sectors.data?.sectors || []).map((s: any) => [s.sector, s]));

  return (
    <div className="space-y-5">
      {/* Market regime */}
      <div className="animate-fade-in">
        {regime.error ? (
          <ErrorState message={regime.error} onRetry={regime.reload} />
        ) : (
          <div className="glass-card-static p-4 flex flex-wrap items-center justify-between gap-3" style={{ borderLeft: `3px solid ${color}` }}>
            <div className="flex items-center gap-3 min-w-0">
              <Shield size={20} style={{ color, flexShrink: 0 }} />
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>MARKET REGIME</span>
                  {regime.loading ? <Skeleton className="h-5 w-20" /> : <span className="badge badge-neutral" style={{ color }}>{r?.regime}</span>}
                  {r && <span className="badge badge-info">Mood: {r.mood}</span>}
                </div>
                <p className="text-xs mt-0.5" style={{ color: "var(--text-secondary)" }}>
                  {regime.loading ? "Loading live regime from Upstox…" : evidence.length ? evidence.join(" · ") : "Based on live index, VIX and FII/DII data."}
                </p>
              </div>
            </div>
            <button className="btn-secondary text-xs" onClick={() => navigate("analytics")}>
              View Details <ChevronRight size={14} />
            </button>
          </div>
        )}
      </div>

      {/* Metric cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 stagger-children">
        <MetricCard
          title="NIFTY 50"
          value={fmtNum(idx.nifty_50?.value)}
          change={fmtPct(idx.nifty_50?.change)}
          changeTone={tone(idx.nifty_50?.change)}
          subtitle={`Bank Nifty ${fmtNum(idx.bank_nifty?.value)} (${fmtPct(idx.bank_nifty?.change)})`}
          icon={<LineChart size={16} style={{ color: "var(--accent-indigo)" }} />}
          onClick={() => navigate("analytics")}
          loading={regime.loading}
        />
        <MetricCard
          title="INDIA VIX"
          value={fmtNum(idx.india_vix?.value)}
          change={fmtPct(idx.india_vix?.change)}
          changeTone={tone(idx.india_vix?.change == null ? null : -idx.india_vix.change)}
          subtitle="Volatility index — rising VIX = rising fear"
          icon={<Activity size={16} style={{ color: "var(--accent-cyan)" }} />}
          onClick={() => navigate("analytics")}
          loading={regime.loading}
        />
        <MetricCard
          title="BREADTH (UNIVERSE)"
          value={breadth ? `${breadth.advances} ▲ / ${breadth.declines} ▼` : "—"}
          change={breadth ? `${breadth.above_200dma}/${breadth.total} above 200-DMA` : undefined}
          changeTone={breadth ? (breadth.advances >= breadth.declines ? "bullish" : "bearish") : "neutral"}
          subtitle="Approved sector universe"
          icon={<BarChart3 size={16} style={{ color: "#22c55e" }} />}
          onClick={() => navigate("scanner")}
          loading={movers.loading}
        />
        <MetricCard
          title="FII NET (CASH)"
          value={fii ? fmtINRCompact(fii.net * 1e7) : "—"}
          change={r?.dii_activity ? `DII ${fmtINRCompact(r.dii_activity.net * 1e7)}` : undefined}
          changeTone={tone(fii?.net)}
          subtitle={fii ? `Session ${fii.date}` : "Institutional flows"}
          icon={<Globe size={16} style={{ color: "#f59e0b" }} />}
          onClick={() => navigate("analytics")}
          loading={regime.loading}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Top picks */}
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

        {/* Portfolio & movers */}
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

          <Card padded={false}>
            <div className="px-5 py-4 flex items-center justify-between border-b" style={{ borderColor: "var(--border-subtle)" }}>
              <h3 className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>Top Movers</h3>
              <button className="btn-ghost text-xs" onClick={() => navigate("analytics")}>More <ChevronRight size={14} /></button>
            </div>
            <div className="p-4 space-y-1">
              {movers.loading ? (
                [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-6 w-full" />)
              ) : movers.error ? (
                <ErrorState message={movers.error} onRetry={movers.reload} />
              ) : (
                [...(movers.data?.gainers || []).slice(0, 3), ...(movers.data?.losers || []).slice(0, 3)].map((m: any) => (
                  <div key={m.symbol} className="flex items-center justify-between text-xs py-1">
                    <StockLink symbol={m.symbol} />
                    <span className="tabular-nums" style={{ color: "var(--text-secondary)" }}>{fmtINR(m.ltp)}</span>
                    <Change value={m.change_pct} className="w-16 text-right" />
                  </div>
                ))
              )}
            </div>
          </Card>
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
          Probabilistic estimates, not certainties. No trades are executed automatically. All market data sourced from Upstox APIs.
          Protect capital first — opportunity comes second.
        </p>
      </div>
    </div>
  );
}
