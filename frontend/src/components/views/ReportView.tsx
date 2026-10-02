"use client";

import { useState } from "react";
import Link from "next/link";
import { ChevronRight, Download, FileText, Newspaper, Shield, Target, TrendingDown, TrendingUp } from "lucide-react";
import { marketAPI, signalsAPI } from "@/lib/api";
import { portfolioParams, useAppStore } from "@/lib/store";
import { useApi } from "@/lib/useApi";
import { fmtDate, fmtINR, fmtNum, fmtPct, fmtVolume, humanize, timeAgo } from "@/lib/format";
import { buildRecommendation, verdictColor, verdictLabel } from "@/lib/verdict";
import AICommentary from "../AICommentary";
import OrderTicketDialog, { OrderDefaults } from "../OrderTicketDialog";
import SearchBox from "../SearchBox";
import { Card, Change, EntryBadge, ErrorState, KeyValue, LoadingRows, PageHeader, SectionHeader } from "../ui";

const HORIZONS = ["1D", "5D", "10D", "20D"];
const RECENT_KEY = "stockmind_recent_reports";

function loadRecent(): string[] {
  try {
    return JSON.parse(localStorage.getItem(RECENT_KEY) || "[]");
  } catch {
    return [];
  }
}

function saveRecent(symbol: string, prev: string[]): string[] {
  const next = [symbol, ...prev.filter((x) => x !== symbol)].slice(0, 8);
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch {}
  return next;
}

/** Plain-text/markdown render of the report, for the download button. */
function toMarkdown(symbol: string, q: any, analysis: any, fundamentals: any, news: any[]): string {
  const s = analysis?.signal;
  const ee = s?.entry_exit;
  const lines: string[] = [];
  lines.push(`# ${symbol} — Equity Research Report`);
  lines.push(`Generated ${new Date().toLocaleString("en-IN")} · StockMind AI\n`);

  if (q) {
    lines.push(`## Snapshot`);
    lines.push(`- CMP: ₹${fmtNum(q.ltp)} (${fmtPct(q.change_pct)})`);
    lines.push(`- Day range: ₹${fmtNum(q.ohlc?.low)} – ₹${fmtNum(q.ohlc?.high)}`);
    lines.push(`- Volume: ${fmtVolume(q.volume)}`);
    lines.push(`- ISIN: ${q.isin || "—"}\n`);
  }

  if (analysis?.technical_summary) {
    lines.push(`## Thesis`);
    lines.push(`${analysis.technical_summary}\n`);
  }

  if (s) {
    lines.push(`## Signal & Trade Plan`);
    lines.push(`- Classification: ${humanize(s.signal?.entry)} (${humanize(s.signal?.type)})`);
    lines.push(`- Entry zone: ${ee?.entry_zone ? `₹${fmtNum(ee.entry_zone[0])} – ₹${fmtNum(ee.entry_zone[1])}` : "—"}`);
    lines.push(`- Stop loss: ₹${fmtNum(ee?.stop_loss)}`);
    lines.push(`- Targets: ₹${fmtNum(ee?.target_1)} / ₹${fmtNum(ee?.target_2)}`);
    lines.push(`- Risk:Reward: ${ee?.risk_reward ? `1:${ee.risk_reward}` : "—"}`);
    lines.push(`- Position: ${s.position?.quantity ?? "—"} shares, ₹${fmtNum(s.position?.value, 0)} (risk ₹${fmtNum(s.position?.max_risk, 0)})`);
    lines.push(`- Thesis invalidation: ${s.thesis_invalidation || "—"}\n`);
    lines.push(`### Supporting evidence`);
    (s.evidence?.positive || []).forEach((e: any) => lines.push(`- ${e.factor}`));
    lines.push(`### Opposing evidence`);
    (s.evidence?.negative || []).forEach((e: any) => lines.push(`- ${e.factor}`));
    lines.push("");
  }

  if (analysis?.predictions) {
    lines.push(`## Multi-Horizon Model Outlook`);
    for (const h of HORIZONS) {
      const p = analysis.predictions[h];
      if (!p) continue;
      lines.push(
        `- ${h}: up ${(p.direction_probabilities.up * 100).toFixed(1)}% / flat ${(p.direction_probabilities.flat * 100).toFixed(1)}% / down ${(p.direction_probabilities.down * 100).toFixed(1)}% — ${humanize(p.signal)} (${p.confidence} confidence)`
      );
    }
    lines.push("");
  }

  if (fundamentals) {
    lines.push(`## Fundamentals`);
    if (fundamentals.profile?.company_profile) lines.push(`${fundamentals.profile.company_profile}\n`);
    (fundamentals.key_ratios || []).forEach((r: any) => lines.push(`- ${r.name}: ${r.company_value ?? "—"} (sector ${r.sector_value ?? "—"})`));
    lines.push("");
  }

  if (news?.length) {
    lines.push(`## Recent News`);
    news.slice(0, 8).forEach((n: any) => lines.push(`- [${n.heading}](${n.url}) — ${fmtDate(n.published_at)}`));
    lines.push("");
  }

  lines.push(`---\n*${analysis?._disclaimer || "This analysis uses computed technical indicators and statistical models. Predictions are probabilistic, not deterministic."}*`);
  return lines.join("\n");
}

function downloadText(filename: string, content: string) {
  const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function ReportView() {
  const { settings } = useAppStore();
  const [symbol, setSymbol] = useState("");
  const [recent, setRecent] = useState<string[]>(() => (typeof window !== "undefined" ? loadRecent() : []));
  const [order, setOrder] = useState<{ side: "BUY" | "SELL"; defaults: OrderDefaults } | null>(null);

  const select = (s: string) => {
    setSymbol(s);
    setRecent((prev) => saveRecent(s, prev));
  };

  const quote = useApi(() => marketAPI.quote(symbol), [symbol], { enabled: !!symbol });
  const analysis = useApi(() => signalsAPI.analyze(symbol, portfolioParams(settings)), [symbol, settings.capital, settings.riskPct], { enabled: !!symbol });
  const fundamentals = useApi(() => marketAPI.fundamentals(symbol), [symbol], { enabled: !!symbol });
  const news = useApi(() => marketAPI.stockNews(symbol), [symbol], { enabled: !!symbol });

  const q = quote.data;
  const a = analysis.data;
  const f = fundamentals.data;
  const newsItems: any[] = news.data?.news || [];
  const s = a?.signal;
  const ee = s?.entry_exit;

  const loading = symbol && (quote.loading || analysis.loading);

  return (
    <div className="space-y-5">
      <PageHeader
        title="Stock Report"
        subtitle="Full research-style document for a single stock — thesis, trade plan, multi-horizon outlook, fundamentals and news in one place."
      />

      <Card>
        <div className="flex flex-col md:flex-row gap-3 md:items-center">
          <SearchBox className="w-full md:max-w-md" placeholder="Search a stock to generate its report (e.g. RELIANCE)…" onSelect={select} />
          {recent.length > 0 && (
            <div className="flex flex-wrap gap-2 items-center">
              <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>Recent:</span>
              {recent.map((sym) => (
                <button key={sym} className={`chip ${sym === symbol ? "chip-active" : ""}`} onClick={() => select(sym)}>{sym}</button>
              ))}
            </div>
          )}
        </div>
      </Card>

      {!symbol && (
        <Card>
          <div className="flex flex-col items-center justify-center text-center py-10">
            <FileText size={28} style={{ color: "var(--accent-indigo)" }} className="mb-3" />
            <p className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>No stock selected</p>
            <p className="text-xs max-w-md mt-1" style={{ color: "var(--text-muted)" }}>Search for a stock above to generate a full analysis document.</p>
          </div>
        </Card>
      )}

      {symbol && (quote.error || analysis.error) && (
        <ErrorState message={quote.error || analysis.error} onRetry={() => { quote.reload(); analysis.reload(); }} />
      )}

      {symbol && loading && (
        <Card>
          <LoadingRows rows={10} />
        </Card>
      )}

      {symbol && !loading && a && (
        <Card className="space-y-6">
          {/* Document header */}
          <div className="flex flex-wrap items-start justify-between gap-4 pb-4 border-b" style={{ borderColor: "var(--border-subtle)" }}>
            <div>
              <p className="text-[11px] uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>Equity Research Report</p>
              <div className="flex items-center gap-2 mt-1">
                <h2 className="text-2xl font-bold" style={{ color: "var(--text-primary)" }}>{symbol}</h2>
                {q?.name && <span className="text-sm" style={{ color: "var(--text-muted)" }}>{q.name}</span>}
              </div>
              <p className="text-[11px] mt-1" style={{ color: "var(--text-muted)" }}>
                Generated {new Date().toLocaleString("en-IN")} · Regime {humanize(a.metadata?.regime)} · {a.metadata?.candles_used} daily candles
              </p>
            </div>
            <div className="flex items-center gap-3">
              {q && (
                <div className="text-right">
                  <p className="text-2xl font-bold tabular-nums" style={{ color: "var(--text-primary)" }}>{fmtINR(q.ltp)}</p>
                  <Change value={q.change_pct} className="text-sm" />
                </div>
              )}
              <button
                className="btn-secondary text-xs"
                style={{ padding: "6px 12px" }}
                onClick={() => downloadText(`${symbol}-report.md`, toMarkdown(symbol, q, a, f, newsItems))}
              >
                <Download size={13} /> Export
              </button>
              <Link href={`/stock/${symbol}`} className="btn-ghost text-xs">
                Live dashboard <ChevronRight size={13} />
              </Link>
            </div>
          </div>

          {/* Verdict */}
          {s && (
            <div
              className="flex flex-wrap items-center justify-between gap-4 p-4 rounded-xl"
              style={{ background: "rgba(99, 102, 241, 0.05)", border: `1px solid ${verdictColor(s.signal?.entry)}40` }}
            >
              <div className="flex items-start gap-3 min-w-0">
                <span
                  className="px-3 py-1.5 rounded-lg text-sm font-bold whitespace-nowrap"
                  style={{ background: `${verdictColor(s.signal?.entry)}20`, color: verdictColor(s.signal?.entry) }}
                >
                  {verdictLabel(s.signal?.entry).toUpperCase()}
                </span>
                <p className="text-sm leading-relaxed" style={{ color: "var(--text-primary)" }}>
                  {buildRecommendation({
                    entry: s.signal?.entry,
                    evidence: s.evidence,
                    explanation: a.technical_summary,
                    probability_up: a.predictions?.["5D"]?.direction_probabilities?.up,
                    risk_reward: ee?.risk_reward,
                  })}
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <button
                  className="btn-primary text-xs"
                  style={{ padding: "7px 14px", background: "var(--color-bullish)" }}
                  onClick={() =>
                    setOrder({
                      side: "BUY",
                      defaults: {
                        quantity: s.position?.quantity || 1,
                        price: ee?.entry_zone?.[1] ?? q?.ltp,
                        product: "DELIVERY",
                        target: ee?.target_1,
                        stopLoss: ee?.stop_loss,
                      },
                    })
                  }
                >
                  <TrendingUp size={13} /> Buy
                </button>
                <button
                  className="btn-secondary text-xs"
                  style={{ padding: "7px 14px", color: "var(--color-bearish)" }}
                  onClick={() =>
                    setOrder({
                      side: "SELL",
                      defaults: { quantity: s.position?.quantity || 1, price: ee?.entry_zone?.[0] ?? q?.ltp, product: "DELIVERY" },
                    })
                  }
                >
                  <TrendingDown size={13} /> Sell
                </button>
              </div>
            </div>
          )}
          {!s && (
            <p className="text-xs" style={{ color: "var(--color-bearish)" }}>
              No signal data returned for {symbol} — Buy/Sell isn&apos;t available until the analysis loads successfully. Try reloading this report.
            </p>
          )}

          {/* Thesis */}
          {a.technical_summary && (
            <div className="space-y-3">
              <SectionHeader title="Thesis" />
              <p className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>{a.technical_summary}</p>
              <AICommentary symbol={symbol} />
            </div>
          )}

          {/* Trade plan */}
          {s && (
            <div>
              <SectionHeader
                icon={<Target size={16} />}
                title="Signal & Trade Plan"
                actions={<EntryBadge entry={s.signal?.entry} />}
              />
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                <KeyValue label="Entry zone" value={ee?.entry_zone ? `${fmtNum(ee.entry_zone[0])} – ${fmtNum(ee.entry_zone[1])}` : "—"} />
                <KeyValue label="Stop loss" value={fmtINR(ee?.stop_loss)} valueColor="var(--color-bearish)" />
                <KeyValue label="Target 1 / 2" value={`${fmtNum(ee?.target_1)} / ${fmtNum(ee?.target_2)}`} valueColor="var(--color-bullish)" />
                <KeyValue label="Risk : reward" value={ee?.risk_reward ? `1 : ${ee.risk_reward}` : "—"} />
                <KeyValue label="Quantity" value={s.position?.quantity ?? "—"} />
                <KeyValue label="Position value" value={fmtINR(s.position?.value, 0)} />
                <KeyValue label="Capital at risk" value={fmtINR(s.position?.max_risk, 0)} />
                <KeyValue label="RSI / ADX" value={`${fmtNum(s.technical?.rsi, 1)} / ${fmtNum(s.technical?.adx, 1)}`} />
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <p className="text-[11px] font-bold uppercase mb-2 text-bullish flex items-center gap-1"><TrendingUp size={12} /> Supporting evidence</p>
                  <ul className="space-y-1">
                    {(s.evidence?.positive || []).map((e: any, i: number) => <li key={i} className="text-xs" style={{ color: "var(--text-secondary)" }}>• {e.factor}</li>)}
                    {!s.evidence?.positive?.length && <li className="text-xs text-muted">None identified</li>}
                  </ul>
                </div>
                <div>
                  <p className="text-[11px] font-bold uppercase mb-2 text-bearish flex items-center gap-1"><TrendingDown size={12} /> Opposing evidence</p>
                  <ul className="space-y-1">
                    {(s.evidence?.negative || []).map((e: any, i: number) => <li key={i} className="text-xs" style={{ color: "var(--text-secondary)" }}>• {e.factor}</li>)}
                    {!s.evidence?.negative?.length && <li className="text-xs text-muted">None identified</li>}
                  </ul>
                </div>
              </div>
              {s.thesis_invalidation && (
                <p className="text-[11px] mt-3" style={{ color: "var(--text-muted)" }}>Thesis invalidation: {s.thesis_invalidation}</p>
              )}
            </div>
          )}

          {/* Multi-horizon outlook */}
          {a.predictions && (
            <div>
              <SectionHeader title="Multi-Horizon Model Outlook" subtitle="Direction probabilities — not a price target" />
              <div className="table-scroll">
                <table className="data-table">
                  <thead><tr><th>Horizon</th><th>Up</th><th>Flat</th><th>Down</th><th>Expected return</th><th>Signal</th><th>Confidence</th></tr></thead>
                  <tbody>
                    {HORIZONS.filter((h) => a.predictions[h]).map((h) => {
                      const p = a.predictions[h];
                      const dp = p.direction_probabilities;
                      return (
                        <tr key={h}>
                          <td className="font-semibold">{h}</td>
                          <td className="tabular-nums text-bullish">{(dp.up * 100).toFixed(1)}%</td>
                          <td className="tabular-nums text-neutral-warn">{(dp.flat * 100).toFixed(1)}%</td>
                          <td className="tabular-nums text-bearish">{(dp.down * 100).toFixed(1)}%</td>
                          <td className="tabular-nums">{p.expected_return != null ? fmtPct(p.expected_return * 100) : "—"}</td>
                          <td><span className={`badge ${p.signal?.includes("upside") ? "badge-bullish" : p.signal?.includes("downside") ? "badge-bearish" : "badge-neutral"}`}>{humanize(p.signal)}</span></td>
                          <td className="text-xs">{p.confidence}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Fundamentals */}
          {f && (
            <div>
              <SectionHeader title="Fundamentals" subtitle={f.profile?.sector} />
              {f.profile?.company_profile && (
                <p className="text-xs leading-relaxed mb-4" style={{ color: "var(--text-secondary)" }}>{f.profile.company_profile}</p>
              )}
              {Array.isArray(f.key_ratios) && f.key_ratios.length > 0 && (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {f.key_ratios.map((r: any) => (
                    <div key={r.name} className="p-2 rounded-lg" style={{ background: "rgba(255,255,255,0.02)", border: "1px solid var(--border-subtle)" }}>
                      <p className="text-[10px]" style={{ color: "var(--text-muted)" }}>{r.name}</p>
                      <p className="text-sm font-bold tabular-nums" style={{ color: "var(--text-primary)" }}>{r.company_value ?? "—"}</p>
                      <p className="text-[10px]" style={{ color: "var(--text-muted)" }}>Sector {r.sector_value ?? "—"}</p>
                    </div>
                  ))}
                </div>
              )}
              {f.unavailable?.length > 0 && (
                <p className="text-[10px] mt-3" style={{ color: "var(--text-muted)" }}>Not available from Upstox: {f.unavailable.map(humanize).join(", ")}</p>
              )}
            </div>
          )}

          {/* News */}
          <div>
            <SectionHeader icon={<Newspaper size={16} />} title="Recent News" />
            {news.loading ? (
              <LoadingRows rows={3} />
            ) : newsItems.length === 0 ? (
              <p className="text-xs" style={{ color: "var(--text-muted)" }}>No recent news for this stock.</p>
            ) : (
              <ul className="space-y-2">
                {newsItems.slice(0, 8).map((n: any) => (
                  <li key={n.url || n.heading} className="text-xs">
                    <a href={n.url} target="_blank" rel="noopener noreferrer" className="font-semibold hover:underline" style={{ color: "var(--text-primary)" }}>{n.heading}</a>
                    <span style={{ color: "var(--text-muted)" }}> · {timeAgo(n.published_at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="glass-card-static p-3 flex items-start gap-3" style={{ borderLeft: "3px solid var(--color-info)" }}>
            <Shield size={16} style={{ color: "var(--color-info)", flexShrink: 0, marginTop: 1 }} />
            <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
              {a._disclaimer || "This analysis uses computed technical indicators and statistical models. Predictions are probabilistic, not deterministic."}
            </p>
          </div>
        </Card>
      )}

      {order && (
        <OrderTicketDialog
          open={!!order}
          onClose={() => setOrder(null)}
          symbol={symbol}
          side={order.side}
          defaults={order.defaults}
        />
      )}
    </div>
  );
}
