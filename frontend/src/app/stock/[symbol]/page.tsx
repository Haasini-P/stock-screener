"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, BellPlus, Brain, Building2, ExternalLink, Layers, Newspaper, Target, TrendingDown, TrendingUp } from "lucide-react";
import AppShell from "@/components/AppShell";
import AlertDialog from "@/components/AlertDialog";
import CandlestickChart from "@/components/CandlestickChart";
import { Card, EntryBadge, ErrorState, KeyValue, LoadingRows, RefreshButton, SectionHeader, Skeleton } from "@/components/ui";
import { marketAPI, signalsAPI } from "@/lib/api";
import { portfolioParams, useAppStore } from "@/lib/store";
import { useApi } from "@/lib/useApi";
import { fmtDate, fmtINR, fmtNum, fmtPct, fmtVolume, humanize, timeAgo, toneColor } from "@/lib/format";

const HORIZONS = ["1D", "3D", "5D", "10D", "20D"];

function PriceChart({ symbol }: { symbol: string }) {
  return (
    <Card>
      <CandlestickChart symbol={symbol} />
    </Card>
  );
}

function PredictionCard({ symbol }: { symbol: string }) {
  const [horizon, setHorizon] = useState("5D");
  const pred = useApi(() => marketAPI.prediction(symbol, horizon), [symbol, horizon]);
  const p = pred.data;
  return (
    <Card>
      <SectionHeader
        icon={<Brain size={16} />}
        title="Model prediction"
        subtitle="Direction probabilities — not a price target"
        actions={HORIZONS.map((h) => (
          <button key={h} className={`chip ${horizon === h ? "chip-active" : ""}`} onClick={() => setHorizon(h)}>{h}</button>
        ))}
      />
      {pred.loading ? (
        <LoadingRows rows={3} />
      ) : pred.error ? (
        <ErrorState message={pred.error} onRetry={pred.reload} />
      ) : p ? (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-3">
            {([["up", "Upside", "bullish"], ["flat", "Flat", "neutral"], ["down", "Downside", "bearish"]] as const).map(([k, label, t]) => (
              <div key={k} className="text-center p-3 rounded-lg" style={{ background: `var(--color-${t}-bg)` }}>
                <p className={`text-xl font-bold ${t === "bullish" ? "text-bullish" : t === "bearish" ? "text-bearish" : "text-neutral-warn"}`}>
                  {(p.direction_probabilities[k] * 100).toFixed(1)}%
                </p>
                <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>{label}</p>
              </div>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            <span className="badge badge-info">{p.confidence} confidence</span>
            <span className="badge badge-neutral">{p.risk} risk</span>
            <span className={`badge ${p.signal.includes("upside") ? "badge-bullish" : p.signal.includes("downside") ? "badge-bearish" : "badge-neutral"}`}>{humanize(p.signal)}</span>
            <span className="badge badge-accent">90% range {fmtPct(p.prediction_interval.lower * 100)} to {fmtPct(p.prediction_interval.upper * 100)}</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {([["bull", "🟢 Bull case"], ["base", "🟡 Base case"], ["bear", "🔴 Bear case"]] as const).map(([k, label]) => (
              <div key={k} className="p-3 rounded-lg text-[11px]" style={{ background: "rgba(255,255,255,0.02)", border: "1px solid var(--border-subtle)", color: "var(--text-secondary)" }}>
                <p className="font-bold mb-1" style={{ color: "var(--text-primary)" }}>{label}</p>
                {p.scenarios[k]}
              </div>
            ))}
          </div>
          <p className="text-xs leading-relaxed" style={{ color: "var(--text-secondary)" }}>{p.explanation}</p>
        </div>
      ) : null}
    </Card>
  );
}

function TradePlanCard({ symbol }: { symbol: string }) {
  const { settings } = useAppStore();
  const analysis = useApi(() => signalsAPI.analyze(symbol, portfolioParams(settings)), [symbol, settings.capital, settings.riskPct]);
  const s = analysis.data?.signal;
  const ee = s?.entry_exit;
  return (
    <Card>
      <SectionHeader
        icon={<Target size={16} />}
        title="Signal & trade plan"
        subtitle={analysis.data ? `Regime ${analysis.data.metadata.regime} · ${analysis.data.metadata.candles_used} daily candles · capital ${fmtINR(settings.capital, 0)} @ ${settings.riskPct}% risk` : undefined}
      />
      {analysis.loading ? (
        <LoadingRows rows={4} />
      ) : analysis.error ? (
        <ErrorState message={analysis.error} onRetry={analysis.reload} />
      ) : s ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <EntryBadge entry={s.signal.entry} />
            <span className="badge badge-neutral">{humanize(s.signal.type)}</span>
            <span className="badge badge-info">{s.technical.trend}</span>
            <span className="badge badge-neutral">{s.prediction.confidence} confidence · {s.prediction.risk} risk</span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KeyValue label="Entry zone" value={ee.entry_zone?.[0] ? `${fmtNum(ee.entry_zone[0])} – ${fmtNum(ee.entry_zone[1])}` : "—"} />
            <KeyValue label="Stop loss" value={fmtINR(ee.stop_loss)} valueColor="var(--color-bearish)" />
            <KeyValue label="Target 1 / 2" value={`${fmtNum(ee.target_1)} / ${fmtNum(ee.target_2)}`} valueColor="var(--color-bullish)" />
            <KeyValue label="Risk : reward" value={ee.risk_reward ? `1 : ${ee.risk_reward}` : "—"} />
            <KeyValue label="Quantity" value={s.position.quantity || "—"} />
            <KeyValue label="Position value" value={fmtINR(s.position.value, 0)} />
            <KeyValue label="Capital at risk" value={fmtINR(s.position.max_risk, 0)} />
            <KeyValue label="RSI / ADX" value={`${fmtNum(s.technical.rsi, 1)} / ${fmtNum(s.technical.adx, 1)}`} />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <p className="text-[11px] font-bold uppercase mb-2 text-bullish flex items-center gap-1"><TrendingUp size={12} /> Supporting evidence</p>
              <ul className="space-y-1">
                {s.evidence.positive.map((e: any, i: number) => <li key={i} className="text-xs" style={{ color: "var(--text-secondary)" }}>• {e.factor}</li>)}
                {!s.evidence.positive.length && <li className="text-xs text-muted">None</li>}
              </ul>
            </div>
            <div>
              <p className="text-[11px] font-bold uppercase mb-2 text-bearish flex items-center gap-1"><TrendingDown size={12} /> Opposing evidence</p>
              <ul className="space-y-1">
                {s.evidence.negative.map((e: any, i: number) => <li key={i} className="text-xs" style={{ color: "var(--text-secondary)" }}>• {e.factor}</li>)}
                {!s.evidence.negative.length && <li className="text-xs text-muted">None</li>}
              </ul>
            </div>
          </div>
          {s.technical.summary && <p className="text-xs" style={{ color: "var(--text-secondary)" }}>{s.technical.summary}</p>}
          {s.thesis_invalidation && <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>Invalidation: {s.thesis_invalidation}</p>}
        </div>
      ) : null}
    </Card>
  );
}

function FundamentalsCard({ symbol }: { symbol: string }) {
  const f = useApi(() => marketAPI.fundamentals(symbol), [symbol]);
  const d = f.data;
  const income = d?.income_statement;
  const rows: any[] = (income?.income_statement || []).slice(0, 6);
  const periods: string[] = rows[0]?.history?.slice(0, 4).map((h: any) => h.period) || [];

  return (
    <Card>
      <SectionHeader icon={<Building2 size={16} />} title="Fundamentals" subtitle={d?.profile?.sector} />
      {f.loading ? (
        <LoadingRows rows={5} />
      ) : f.error ? (
        <ErrorState message={f.error} onRetry={f.reload} />
      ) : d ? (
        <div className="space-y-5">
          {d.profile?.company_profile && (
            <p className="text-xs leading-relaxed line-clamp-4" style={{ color: "var(--text-secondary)" }} title={d.profile.company_profile}>
              {d.profile.company_profile}
            </p>
          )}

          {Array.isArray(d.key_ratios) && d.key_ratios.length > 0 && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {d.key_ratios.map((r: any) => (
                <div key={r.name} className="p-2 rounded-lg" style={{ background: "rgba(255,255,255,0.02)", border: "1px solid var(--border-subtle)" }}>
                  <p className="text-[10px]" style={{ color: "var(--text-muted)" }}>{r.name}</p>
                  <p className="text-sm font-bold tabular-nums" style={{ color: "var(--text-primary)" }}>{r.company_value ?? "—"}</p>
                  <p className="text-[10px]" style={{ color: "var(--text-muted)" }}>Sector {r.sector_value ?? "—"}</p>
                </div>
              ))}
            </div>
          )}

          {rows.length > 0 && (
            <div className="table-scroll">
              <p className="text-[11px] font-bold uppercase mb-2" style={{ color: "var(--text-muted)" }}>
                Income statement ({income.time_period}, ₹ {income.units_in})
              </p>
              <table className="data-table">
                <thead><tr><th>Item</th>{periods.map((p) => <th key={p}>{p}</th>)}</tr></thead>
                <tbody>
                  {rows.map((r: any) => (
                    <tr key={r.category}>
                      <td className="text-xs">{humanize(r.category)}</td>
                      {r.history.slice(0, 4).map((h: any) => (
                        <td key={h.period} className="tabular-nums text-xs">
                          {fmtNum(h.value, 0)}
                          {h.change && <div className="text-[10px]" style={{ color: h.change.startsWith("-") ? "var(--color-bearish)" : "var(--color-bullish)" }}>{h.change}</div>}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {Array.isArray(d.shareholding) && d.shareholding.length > 0 && (
            <div>
              <p className="text-[11px] font-bold uppercase mb-2" style={{ color: "var(--text-muted)" }}>
                Shareholding ({d.shareholding[0]?.history?.[0]?.period})
              </p>
              <div className="flex flex-wrap gap-2">
                {d.shareholding.map((s: any) => {
                  const [latest, prev] = s.history || [];
                  const delta = latest && prev ? latest.value - prev.value : null;
                  return (
                    <span key={s.category} className="badge badge-neutral" style={{ color: "var(--text-primary)" }}>
                      {humanize(s.category)} {fmtNum(latest?.value)}%
                      {delta != null && delta !== 0 && <span style={{ color: toneColor(delta) }}>&nbsp;({delta > 0 ? "+" : ""}{delta.toFixed(2)})</span>}
                    </span>
                  );
                })}
              </div>
            </div>
          )}

          {Array.isArray(d.corporate_actions) && d.corporate_actions.length > 0 && (
            <div>
              <p className="text-[11px] font-bold uppercase mb-2" style={{ color: "var(--text-muted)" }}>Corporate actions</p>
              <ul className="space-y-1">
                {d.corporate_actions.slice(0, 5).map((a: any, i: number) => (
                  <li key={i} className="flex justify-between text-xs" style={{ color: "var(--text-secondary)" }}>
                    <span>{a.name}{a.amount ? ` · ₹${a.amount}` : ""}{a.ratio ? ` · ${a.ratio}` : ""}</span>
                    <span style={{ color: "var(--text-muted)" }}>{a.expiry_date}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {d.unavailable?.length > 0 && (
            <p className="text-[10px]" style={{ color: "var(--text-muted)" }}>Not available from Upstox: {d.unavailable.map(humanize).join(", ")}</p>
          )}
        </div>
      ) : null}
    </Card>
  );
}

function NewsCard({ symbol }: { symbol: string }) {
  const news = useApi(() => marketAPI.stockNews(symbol), [symbol]);
  const items: any[] = news.data?.news || [];
  return (
    <Card>
      <SectionHeader icon={<Newspaper size={16} />} title="News" subtitle="Source: Upstox" />
      {news.loading ? (
        <LoadingRows rows={3} />
      ) : news.error ? (
        <ErrorState message={news.error} onRetry={news.reload} />
      ) : items.length === 0 ? (
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>No recent news for this stock.</p>
      ) : (
        <ul className="space-y-3">
          {items.slice(0, 8).map((n, i) => (
            <li key={`${n.url || n.heading || "news"}-${i}`}>
              <a href={n.url} target="_blank" rel="noopener noreferrer" className="text-xs font-semibold hover:underline inline-flex gap-1" style={{ color: "var(--text-primary)" }}>
                {n.heading} <ExternalLink size={11} className="shrink-0 mt-0.5" style={{ color: "var(--text-muted)" }} />
              </a>
              <p className="text-[10px]" style={{ color: "var(--text-muted)" }}>{timeAgo(n.published_at)} · {fmtDate(n.published_at)}</p>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function DepthSide({ rows, side, maxQty }: { rows: any[]; side: "buy" | "sell"; maxQty: number }) {
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-[10px] font-semibold uppercase" style={{ color: "var(--text-muted)" }}>
        <span>{side === "buy" ? "Bid" : "Ask"}</span><span>Qty</span>
      </div>
      {rows.map((r, i) => (
        <div key={i} className="relative flex justify-between text-xs tabular-nums px-1 py-0.5">
          <div
            className="absolute inset-y-0 rounded"
            style={{ [side === "buy" ? "right" : "left"]: 0, width: `${(r.quantity / maxQty) * 100}%`, background: side === "buy" ? "var(--color-bullish-bg)" : "var(--color-bearish-bg)" }}
          />
          <span className="relative" style={{ color: side === "buy" ? "var(--color-bullish)" : "var(--color-bearish)" }}>{fmtNum(r.price)}</span>
          <span className="relative" style={{ color: "var(--text-secondary)" }}>{r.quantity.toLocaleString("en-IN")}</span>
        </div>
      ))}
    </div>
  );
}

function DepthCard({ depth }: { depth: any }) {
  const buy: any[] = depth?.buy || [];
  const sell: any[] = depth?.sell || [];
  if (!buy.length && !sell.length) return null;
  const maxQty = Math.max(1, ...buy.map((b) => b.quantity), ...sell.map((s) => s.quantity));
  return (
    <Card>
      <SectionHeader icon={<Layers size={16} />} title="Market depth" />
      <div className="grid grid-cols-2 gap-4">
        <DepthSide rows={buy} side="buy" maxQty={maxQty} />
        <DepthSide rows={sell} side="sell" maxQty={maxQty} />
      </div>
    </Card>
  );
}

export default function StockAnalysisPage() {
  const params = useParams();
  const router = useRouter();
  const symbol = decodeURIComponent((params?.symbol as string) || "").toUpperCase();
  const { settings } = useAppStore();
  const [alertOpen, setAlertOpen] = useState(false);
  const quote = useApi(() => marketAPI.quote(symbol), [symbol], { refreshMs: settings.refreshSec * 1000 });
  const q = quote.data;

  useEffect(() => {
    document.title = `${symbol} · StockMind AI`;
  }, [symbol]);

  return (
    <AppShell>
      <div className="space-y-5 animate-fade-in">
        {/* Header */}
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <button className="btn-ghost mt-1" onClick={() => (window.history.length > 1 ? router.back() : router.push("/"))} aria-label="Back">
              <ArrowLeft size={18} />
            </button>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-bold" style={{ color: "var(--text-primary)" }}>{symbol}</h1>
                <span className="badge badge-info">NSE</span>
              </div>
              <p className="text-xs" style={{ color: "var(--text-muted)" }}>{q?.name || (quote.loading ? "Loading…" : "")}{q?.isin ? ` · ${q.isin}` : ""}</p>
              {quote.loading ? (
                <Skeleton className="h-8 w-40 mt-2" />
              ) : q ? (
                <div className="flex items-baseline gap-3 mt-1">
                  <span className="text-3xl font-bold tabular-nums" style={{ color: "var(--text-primary)" }}>{fmtINR(q.ltp)}</span>
                  <span className="text-sm font-semibold tabular-nums" style={{ color: toneColor(q.change) }}>
                    {q.change != null ? `${q.change > 0 ? "+" : ""}${fmtNum(q.change)}` : ""} ({fmtPct(q.change_pct)})
                  </span>
                </div>
              ) : null}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <RefreshButton onClick={quote.reload} busy={quote.refreshing} updatedAt={quote.updatedAt} />
            <button className="btn-primary text-xs" style={{ padding: "7px 14px" }} onClick={() => setAlertOpen(true)} disabled={!q}>
              <BellPlus size={14} /> Set alert
            </button>
          </div>
        </div>

        {quote.error ? (
          <ErrorState message={quote.error} onRetry={quote.reload} />
        ) : (
          <>
            {q && (
              <Card>
                <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-4">
                  <KeyValue label="Open" value={fmtNum(q.ohlc?.open)} />
                  <KeyValue label="High" value={fmtNum(q.ohlc?.high)} />
                  <KeyValue label="Low" value={fmtNum(q.ohlc?.low)} />
                  <KeyValue label="Prev close" value={fmtNum(q.prev_close)} />
                  <KeyValue label="Volume" value={fmtVolume(q.volume)} />
                  <KeyValue label="Avg price" value={fmtNum(q.average_price)} />
                  <KeyValue label="Lower circuit" value={fmtNum(q.lower_circuit)} />
                  <KeyValue label="Upper circuit" value={fmtNum(q.upper_circuit)} />
                </div>
              </Card>
            )}

            <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
              <div className="xl:col-span-2 space-y-5">
                <PriceChart symbol={symbol} />
                <TradePlanCard symbol={symbol} />
                <PredictionCard symbol={symbol} />
              </div>
              <div className="space-y-5">
                <DepthCard depth={q?.depth} />
                <FundamentalsCard symbol={symbol} />
                <NewsCard symbol={symbol} />
              </div>
            </div>
          </>
        )}

        <p className="text-[11px] text-center" style={{ color: "var(--text-muted)" }}>
          Analytical decision-support only. Probabilities are estimates, not certainties. Data: Upstox.
        </p>
      </div>
      <AlertDialog open={alertOpen} onClose={() => setAlertOpen(false)} symbol={symbol} currentPrice={q?.ltp} />
    </AppShell>
  );
}
