"use client";

import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CalendarDays, Gauge, Landmark, TrendingDown, TrendingUp, Volume2 } from "lucide-react";
import { marketAPI, signalsAPI } from "@/lib/api";
import { useAppStore } from "@/lib/store";
import { useApi } from "@/lib/useApi";
import { fmtDate, fmtINR, fmtINRCompact, fmtNum, fmtPct, humanize, toneColor } from "@/lib/format";
import { Card, Change, ErrorState, LoadingRows, PageHeader, RefreshButton, SectionHeader, Skeleton, StockLink } from "../ui";
import { regimeColor } from "./DashboardView";

const INDEX_LABELS: Record<string, string> = {
  nifty_50: "Nifty 50",
  bank_nifty: "Bank Nifty",
  nifty_midcap: "Nifty Midcap 100",
  nifty_smallcap: "Nifty Smallcap 100",
  india_vix: "India VIX",
};

const tooltipStyle = {
  contentStyle: { background: "#111318", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, fontSize: 12 },
  labelStyle: { color: "#f1f3f9" },
};

function MoverList({ title, icon, rows, metric }: { title: string; icon: React.ReactNode; rows: any[]; metric: "change" | "volume" }) {
  return (
    <Card>
      <SectionHeader icon={icon} title={title} />
      {rows.length === 0 ? (
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>None today.</p>
      ) : (
        <div className="space-y-2">
          {rows.map((r) => (
            <div key={r.symbol} className="flex items-center justify-between text-xs">
              <div className="min-w-0">
                <StockLink symbol={r.symbol} />
                <div className="text-[10px] truncate" style={{ color: "var(--text-muted)" }}>{r.sector}</div>
              </div>
              <span className="tabular-nums" style={{ color: "var(--text-secondary)" }}>{fmtINR(r.ltp)}</span>
              {metric === "change" ? (
                <Change value={r.change_pct} className="w-16 text-right" />
              ) : (
                <span className="w-16 text-right font-semibold tabular-nums" style={{ color: "var(--color-neutral)" }}>{fmtNum(r.volume_ratio)}×</span>
              )}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

export default function AnalyticsView() {
  const { settings } = useAppStore();
  const refreshMs = settings.refreshSec ? Math.max(settings.refreshSec * 1000, 60000) : 0;
  const [period, setPeriod] = useState<"change_pct" | "return_5d" | "return_20d">("change_pct");

  const regime = useApi(() => signalsAPI.regime(), [], { refreshMs });
  const movers = useApi(() => marketAPI.movers(8), [], { refreshMs });
  const sectors = useApi(() => marketAPI.sectors(), [], { refreshMs });
  const status = useApi(() => marketAPI.status(), []);

  const r = regime.data;
  const flows = (r?.fii_activity?.history || [])
    .slice(0, 10)
    .reverse()
    .map((f: any, i: number) => ({
      date: f.date.slice(5),
      FII: f.net,
      DII: r?.dii_activity?.history?.slice(0, 10).reverse()[i]?.net ?? null,
    }));
  const sectorData = (sectors.data?.sectors || [])
    .filter((s: any) => s[period] != null)
    .map((s: any) => ({ sector: s.sector, value: s[period] }))
    .sort((a: any, b: any) => b.value - a.value);
  const breadth = movers.data?.breadth;

  return (
    <div className="space-y-5">
      <PageHeader
        title="Market Analytics"
        subtitle="Indices, institutional flows, breadth and sector rotation — live from Upstox"
        actions={
          <RefreshButton
            onClick={() => {
              regime.reload();
              movers.reload();
              sectors.reload();
              status.reload();
            }}
            busy={regime.refreshing || movers.refreshing || sectors.refreshing}
            updatedAt={regime.updatedAt}
          />
        }
      />

      {regime.error && <ErrorState message={regime.error} onRetry={regime.reload} />}

      {/* Indices */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-4">
        {Object.entries(INDEX_LABELS).map(([key, label]) => {
          const v = r?.indian_market?.[key];
          const invert = key === "india_vix";
          return (
            <Card key={key}>
              <p className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>{label}</p>
              {regime.loading ? (
                <Skeleton className="h-7 w-24 mt-2" />
              ) : (
                <>
                  <p className="text-xl font-bold tabular-nums mt-1" style={{ color: "var(--text-primary)" }}>{fmtNum(v?.value)}</p>
                  <span className="text-xs font-semibold" style={{ color: toneColor(invert && v?.change != null ? -v.change : v?.change) }}>
                    {fmtPct(v?.change)}
                  </span>
                </>
              )}
            </Card>
          );
        })}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Regime */}
        <Card accent={regimeColor(r?.regime)}>
          <SectionHeader icon={<Gauge size={16} />} title="Regime & mood" subtitle={r ? `Data sources: ${r.data_sources?.join(", ")}` : undefined} />
          {regime.loading ? (
            <LoadingRows rows={3} />
          ) : r ? (
            <div className="space-y-3">
              <div className="flex gap-2">
                <span className="badge badge-neutral" style={{ color: regimeColor(r.regime) }}>{r.regime}</span>
                <span className="badge badge-info">Mood: {r.mood}</span>
              </div>
              <ul className="space-y-1.5">
                {[...(r.evidence?.regime || []), ...(r.evidence?.mood || [])].map((e: string, i: number) => (
                  <li key={i} className="text-xs" style={{ color: "var(--text-secondary)" }}>• {e}</li>
                ))}
              </ul>
              {r.risk_alerts?.map((a: any, i: number) => (
                <div key={i} className="p-2 rounded text-xs" style={{ background: "var(--color-bearish-bg)", color: "var(--text-primary)" }}>
                  <strong>{a.trigger}</strong> — {a.action}
                </div>
              ))}
              <div className="flex flex-wrap gap-1 pt-1">
                {Object.entries(r.data_confidence || {}).map(([k, v]) => (
                  <span key={k} className={`badge ${v === "FACT" ? "badge-info" : "badge-neutral"}`} style={{ fontSize: 9 }}>
                    {humanize(k)}: {String(v)}
                  </span>
                ))}
              </div>
            </div>
          ) : null}
        </Card>

        {/* FII / DII */}
        <Card className="lg:col-span-2">
          <SectionHeader
            icon={<Landmark size={16} />}
            title="Institutional flows (cash market, ₹ Cr)"
            subtitle={
              r?.fii_activity
                ? `Latest ${r.fii_activity.date}: FII ${fmtINRCompact(r.fii_activity.net * 1e7)} · DII ${fmtINRCompact((r.dii_activity?.net ?? 0) * 1e7)}`
                : "FII and DII net buying/selling"
            }
          />
          {regime.loading ? (
            <Skeleton className="h-56 w-full" />
          ) : flows.length === 0 ? (
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>Flow data unavailable from Upstox right now.</p>
          ) : (
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={flows}>
                  <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
                  <XAxis dataKey="date" tick={{ fill: "#565d73", fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: "#565d73", fontSize: 11 }} axisLine={false} tickLine={false} width={60} />
                  <Tooltip {...tooltipStyle} formatter={(v: any) => `₹${Number(v).toLocaleString("en-IN")} Cr`} />
                  <ReferenceLine y={0} stroke="rgba(255,255,255,0.2)" />
                  <Bar dataKey="FII" fill="#6366f1" radius={[3, 3, 0, 0]} isAnimationActive={false} />
                  <Bar dataKey="DII" fill="#22d3ee" radius={[3, 3, 0, 0]} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Sector performance */}
        <Card className="lg:col-span-2">
          <SectionHeader
            title="Sector performance"
            subtitle="Average return of approved-universe constituents"
            actions={
              <>
                {([["change_pct", "1D"], ["return_5d", "5D"], ["return_20d", "20D"]] as const).map(([k, l]) => (
                  <button key={k} className={`chip ${period === k ? "chip-active" : ""}`} onClick={() => setPeriod(k)}>{l}</button>
                ))}
              </>
            }
          />
          {sectors.loading ? (
            <Skeleton className="h-64 w-full" />
          ) : sectors.error ? (
            <ErrorState message={sectors.error} onRetry={sectors.reload} />
          ) : (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={sectorData} layout="vertical" margin={{ left: 20 }}>
                  <CartesianGrid stroke="rgba(255,255,255,0.05)" horizontal={false} />
                  <XAxis
                    type="number"
                    domain={[(min: number) => Math.min(0, Math.floor(min)), (max: number) => Math.max(0, Math.ceil(max))]}
                    tick={{ fill: "#565d73", fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                    unit="%"
                  />
                  <YAxis type="category" dataKey="sector" tick={{ fill: "#8b92a5", fontSize: 11 }} axisLine={false} tickLine={false} width={110} />
                  <Tooltip {...tooltipStyle} formatter={(v: any) => `${Number(v).toFixed(2)}%`} cursor={{ fill: "rgba(255,255,255,0.03)" }} />
                  <ReferenceLine x={0} stroke="rgba(255,255,255,0.2)" />
                  <Bar dataKey="value" radius={[0, 3, 3, 0]} isAnimationActive={false}>
                    {sectorData.map((d: any) => (
                      <Cell key={d.sector} fill={d.value >= 0 ? "#22c55e" : "#ef4444"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>

        {/* Breadth + calendar */}
        <div className="space-y-5">
          <Card>
            <SectionHeader title="Breadth (universe)" />
            {breadth ? (
              <>
                <div className="flex h-3 rounded-full overflow-hidden mb-2">
                  <div style={{ width: `${(breadth.advances / Math.max(breadth.total, 1)) * 100}%`, background: "var(--color-bullish)" }} />
                  <div style={{ width: `${(breadth.unchanged / Math.max(breadth.total, 1)) * 100}%`, background: "var(--color-neutral)" }} />
                  <div style={{ width: `${(breadth.declines / Math.max(breadth.total, 1)) * 100}%`, background: "var(--color-bearish)" }} />
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-bullish">{breadth.advances} advancing</span>
                  <span className="text-bearish">{breadth.declines} declining</span>
                </div>
                <p className="text-xs mt-3" style={{ color: "var(--text-secondary)" }}>
                  {breadth.above_200dma} of {breadth.total} stocks trade above their 200-day average.
                </p>
              </>
            ) : (
              <LoadingRows rows={2} />
            )}
          </Card>
          <Card>
            <SectionHeader icon={<CalendarDays size={16} />} title="Market calendar" subtitle={status.data?.status ? `NSE: ${humanize(status.data.status.status?.toLowerCase())}` : undefined} />
            {status.loading ? (
              <LoadingRows rows={3} />
            ) : (
              <ul className="space-y-1.5">
                {(status.data?.upcoming_holidays || []).slice(0, 5).map((h: any) => (
                  <li key={h.date} className="flex justify-between text-xs">
                    <span style={{ color: "var(--text-secondary)" }}>{h.description}</span>
                    <span className="tabular-nums" style={{ color: "var(--text-muted)" }}>{fmtDate(h.date)}</span>
                  </li>
                ))}
                {!status.data?.upcoming_holidays?.length && <li className="text-xs text-muted">No upcoming trading holidays.</li>}
              </ul>
            )}
          </Card>
        </div>
      </div>

      {/* Movers */}
      {movers.error ? (
        <ErrorState message={movers.error} onRetry={movers.reload} />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          <MoverList title="Top gainers" icon={<TrendingUp size={16} />} rows={movers.data?.gainers || []} metric="change" />
          <MoverList title="Top losers" icon={<TrendingDown size={16} />} rows={movers.data?.losers || []} metric="change" />
          <MoverList title="Volume shockers" icon={<Volume2 size={16} />} rows={movers.data?.volume_shockers || []} metric="volume" />
        </div>
      )}
    </div>
  );
}
