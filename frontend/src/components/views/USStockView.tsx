"use client";

/**
 * StockMind AI — US Stocks (Paper Trading & Research)
 *
 * Real quotes/candles/news come from Alpaca's free tier once a key is added
 * in Settings → Broker API Credentials (~15-min delayed IEX data); fundamentals
 * come from SEC EDGAR (free, no key, always on). Until/unless Alpaca is
 * configured, or for a specific fetch failure, each section below falls back
 * to an honest "not available" message rather than the whole page going dark —
 * this is NOT a clone of ReportView.tsx's all-or-nothing data loading.
 *
 * Visually distinguished from the Indian Stock Report with a blue accent
 * (this page's own color, not a shared CSS variable) so it reads as its own
 * report rather than a palette-identical copy.
 *
 * Sections: Universe Browser -> Verdict strip -> Chart -> Technicals -> Trade
 * Plan -> Term Outlook -> Fundamentals (SEC) -> News (Alpaca) -> AI Research
 * Notes -> Paper Trading Desk -> Trade History & Taxes (the last two are
 * unique to this page and unaffected by whether Alpaca is configured, since
 * paper trading never needed a live quote to begin with).
 */

import { useEffect, useState } from "react";
import {
  AlertTriangle, BarChart3, DollarSign, Newspaper, Receipt, Search, Sparkles, Target, TrendingDown, TrendingUp, Zap,
} from "lucide-react";
import {
  PaperOrder, PaperPosition, PaperTaxSummary, PaperTrade, USResearchResult, USScannerRow,
  errorMessage, paperTradingAPI, usMarketAPI,
} from "@/lib/api";
import { useAppStore } from "@/lib/store";
import { useApi } from "@/lib/useApi";
import { fmtDate, fmtINR, fmtPct, fmtUSD, timeAgo } from "@/lib/format";
import CandlestickChart from "../CandlestickChart";
import PaperOrderDialog from "../PaperOrderDialog";
import MarkdownContent from "../MarkdownContent";
import SearchBox from "../SearchBox";
import { Card, EmptyState, EntryBadge, ErrorState, KeyValue, LoadingRows, PageHeader, SectionHeader } from "../ui";

/** USD amount with a small "(≈ ₹...)" suffix when a real FX rate is available —
 * never shown without a real rate (no guessed conversion). */
function dualAmount(usd: number, fxRate: number | null): React.ReactNode {
  return (
    <>
      {fmtUSD(usd)}
      {fxRate != null && <span className="text-[10px]" style={{ color: "var(--text-muted)" }}> (≈{fmtINR(usd * fxRate, 0)})</span>}
    </>
  );
}

const US_ACCENT = "#2563eb"; // this page's own accent — not a shared/global CSS variable
const HORIZONS = ["1D", "5D", "10D", "20D"];

/** Local duplicate of ReportView.tsx's buildTermOutlook (not imported — that
 * file is intentionally left untouched). Same logic: short/medium-term from
 * real 5D/20D model predictions, long-term as a structural (200-day MA) read
 * since no multi-month ML prediction exists for either market. */
type TermVerdict = { term: string; horizon: string; verdict: "Favorable" | "Neutral" | "Unfavorable" | "No data"; badgeClass: string; reason: string };

function classifyDirectional(dp: any, expectedReturn: number | null | undefined): { verdict: TermVerdict["verdict"]; badgeClass: string } {
  if (!dp) return { verdict: "No data", badgeClass: "badge-neutral" };
  const edge = (dp.up ?? 0) - (dp.down ?? 0);
  if (edge > 0.12 && (expectedReturn ?? 0) > 0) return { verdict: "Favorable", badgeClass: "badge-bullish" };
  if (edge < -0.12 && (expectedReturn ?? 0) < 0) return { verdict: "Unfavorable", badgeClass: "badge-bearish" };
  return { verdict: "Neutral", badgeClass: "badge-neutral" };
}

function buildUSTermOutlook(analysis: any): TermVerdict[] {
  const predictions = analysis?.predictions || {};
  const rows: TermVerdict[] = [];

  const p5 = predictions["5D"];
  const dp5 = p5?.direction_probabilities;
  const short = classifyDirectional(dp5, p5?.expected_return);
  rows.push({
    term: "Short-term", horizon: "~5 trading days", verdict: short.verdict, badgeClass: short.badgeClass,
    reason: dp5
      ? `Model: ${(dp5.up * 100).toFixed(0)}% up / ${(dp5.down * 100).toFixed(0)}% down, expected ${p5.expected_return != null ? fmtPct(p5.expected_return * 100) : "—"} (${p5.confidence} confidence)`
      : "No 5D model prediction available",
  });

  const p20 = predictions["20D"];
  const dp20 = p20?.direction_probabilities;
  const medium = classifyDirectional(dp20, p20?.expected_return);
  rows.push({
    term: "Medium-term", horizon: "~20 trading days", verdict: medium.verdict, badgeClass: medium.badgeClass,
    reason: dp20
      ? `Model: ${(dp20.up * 100).toFixed(0)}% up / ${(dp20.down * 100).toFixed(0)}% down, expected ${p20.expected_return != null ? fmtPct(p20.expected_return * 100) : "—"} (${p20.confidence} confidence)`
      : "No 20D model prediction available",
  });

  const snapshot = p20?.feature_snapshot || (Object.values(predictions).find((p: any) => p?.feature_snapshot) as any)?.feature_snapshot;
  const dist200 = snapshot?.dist_sma_200;
  let longVerdict: TermVerdict["verdict"] = "No data";
  let longBadge = "badge-neutral";
  let longReason = "200-day moving average data not available";
  if (dist200 != null) {
    const pct = dist200 * 100;
    if (pct > 3) { longVerdict = "Favorable"; longBadge = "badge-bullish"; }
    else if (pct < -3) { longVerdict = "Unfavorable"; longBadge = "badge-bearish"; }
    else { longVerdict = "Neutral"; longBadge = "badge-neutral"; }
    longReason = `Price is ${Math.abs(pct).toFixed(1)}% ${pct >= 0 ? "above" : "below"} its 200-day moving average — structural read, not a model forecast`;
  }
  rows.push({ term: "Long-term", horizon: "Structural (200-day trend)", verdict: longVerdict, badgeClass: longBadge, reason: longReason });

  return rows;
}

function USResearchNotes({ symbol }: { symbol: string }) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<USResearchResult | null>(null);
  const [error, setError] = useState("");

  const run = async () => {
    setOpen(true);
    if (result || loading) return;
    setLoading(true);
    setError("");
    try {
      const res = await usMarketAPI.research(symbol);
      setResult(res.data);
    } catch (err) {
      setError(errorMessage(err, "Could not generate AI research notes."));
    } finally {
      setLoading(false);
    }
  };

  if (!open) {
    return (
      <button className="btn-ghost text-xs" onClick={run} title={`AI research notes on ${symbol}`}>
        <Sparkles size={12} /> AI Research Notes
      </button>
    );
  }

  const dataBacked = result?.data_backed;
  return (
    <div
      className="p-3 rounded-lg"
      style={
        dataBacked
          ? { background: "rgba(37, 99, 235, 0.06)", border: "1px solid rgba(37, 99, 235, 0.25)" }
          : { background: "rgba(245, 158, 11, 0.06)", border: "1px solid rgba(245, 158, 11, 0.25)" }
      }
    >
      {result && (
        <div
          className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wide"
          style={{ color: dataBacked ? US_ACCENT : "#f59e0b" }}
        >
          <AlertTriangle size={11} />
          {dataBacked ? "Institutional-grade analysis — Alpaca + SEC EDGAR data" : "General knowledge — not live or verified data"}
        </div>
      )}
      {loading ? (
        <p className="text-xs mt-2" style={{ color: "var(--text-muted)" }}>Thinking…</p>
      ) : error ? (
        <p className="text-xs mt-2" style={{ color: "var(--color-bearish)" }}>{error}</p>
      ) : result ? (
        <>
          <div className="mt-2">
            <MarkdownContent content={result.content} />
          </div>
          <p className="text-[10px] mt-2" style={{ color: "var(--text-muted)" }}>
            {result.model}{result.cached ? " · cached" : ""} · {timeAgo(result.generated_at)}
          </p>
        </>
      ) : null}
    </div>
  );
}

function PositionsTable({ positions, fxRate }: { positions: PaperPosition[]; fxRate: number | null }) {
  if (!positions.length) {
    return <p className="text-xs" style={{ color: "var(--text-muted)" }}>No paper positions yet.</p>;
  }
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead><tr><th>Symbol</th><th>Qty</th><th>Avg cost</th><th>Realized P&L</th><th>Est. tax</th><th>After-tax</th></tr></thead>
        <tbody>
          {positions.map((p) => (
            <tr key={p.symbol}>
              <td className="font-semibold">{p.symbol}</td>
              <td className="tabular-nums">{p.quantity}</td>
              <td className="tabular-nums">{dualAmount(p.avg_cost, fxRate)}</td>
              <td className={`tabular-nums ${p.realized_pnl > 0 ? "text-bullish" : p.realized_pnl < 0 ? "text-bearish" : ""}`}>
                {dualAmount(p.realized_pnl, fxRate)}
              </td>
              <td className="tabular-nums" style={{ color: "var(--text-muted)" }}>{dualAmount(p.estimated_tax, fxRate)}</td>
              <td className="tabular-nums font-semibold">{dualAmount(p.realized_pnl - p.estimated_tax, fxRate)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TradesTable({ trades, fxRate }: { trades: PaperTrade[]; fxRate: number | null }) {
  if (!trades.length) {
    return <p className="text-xs" style={{ color: "var(--text-muted)" }}>No closed paper trades yet — sell part of a position to see buy/sell detail and estimated tax here.</p>;
  }
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <th>Symbol</th><th>Qty</th><th>Bought</th><th>Sold</th><th>Held</th><th>Term</th>
            <th>Cost basis</th><th>Proceeds</th><th>Gain</th><th>Est. tax</th><th>After-tax</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t, i) => (
            <tr key={i}>
              <td className="font-semibold">{t.symbol}</td>
              <td className="tabular-nums">{t.quantity}</td>
              <td className="text-xs" style={{ color: "var(--text-muted)" }}>{fmtDate(t.buy_date)}</td>
              <td className="text-xs" style={{ color: "var(--text-muted)" }}>{fmtDate(t.sell_date)}</td>
              <td className="tabular-nums text-xs">{t.holding_days}d</td>
              <td><span className={`badge ${t.term === "long_term" ? "badge-info" : "badge-neutral"}`}>{t.term === "long_term" ? "Long-term" : "Short-term"}</span></td>
              <td className="tabular-nums">{dualAmount(t.cost_basis, fxRate)}</td>
              <td className="tabular-nums">{dualAmount(t.proceeds, fxRate)}</td>
              <td className={`tabular-nums ${t.gain > 0 ? "text-bullish" : t.gain < 0 ? "text-bearish" : ""}`}>{dualAmount(t.gain, fxRate)}</td>
              <td className="tabular-nums" style={{ color: "var(--text-muted)" }}>{dualAmount(t.estimated_tax, fxRate)} <span className="text-[10px]">({(t.tax_rate * 100).toFixed(0)}%)</span></td>
              <td className="tabular-nums font-semibold">{dualAmount(t.after_tax_gain, fxRate)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TaxSummaryStrip({ summary, fxRate }: { summary: PaperTaxSummary; fxRate: number | null }) {
  return (
    <Card className="space-y-3">
      <SectionHeader
        icon={<Receipt size={16} />}
        title="Paper P&L and Estimated Tax"
        subtitle={fxRate ? `All symbols combined, FIFO-matched · $1 ≈ ₹${fxRate.toFixed(2)}` : "All symbols combined, FIFO-matched"}
      />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KeyValue label="Total realized gain" value={dualAmount(summary.total_realized_gain, fxRate)} valueColor={summary.total_realized_gain >= 0 ? "var(--color-bullish)" : "var(--color-bearish)"} />
        <KeyValue label="Estimated tax" value={dualAmount(summary.total_estimated_tax, fxRate)} />
        <KeyValue label="Net after-tax" value={dualAmount(summary.net_after_tax, fxRate)} valueColor={summary.net_after_tax >= 0 ? "var(--color-bullish)" : "var(--color-bearish)"} />
        <KeyValue label="Closed trades" value={summary.closed_trade_count} />
        <KeyValue label="Short-term gain" value={<>{dualAmount(summary.short_term_gain, fxRate)} <span className="text-[10px]">(tax {fmtUSD(summary.short_term_tax)})</span></>} />
        <KeyValue label="Long-term gain" value={<>{dualAmount(summary.long_term_gain, fxRate)} <span className="text-[10px]">(tax {fmtUSD(summary.long_term_tax)})</span></>} />
        <KeyValue label="Open positions" value={summary.open_positions_count} />
        <KeyValue label="Open cost basis" value={dualAmount(summary.open_cost_basis, fxRate)} />
      </div>
      <p className="text-[10px] leading-relaxed" style={{ color: "var(--text-muted)" }}>{summary.disclaimer}</p>
    </Card>
  );
}

function OrdersTable({ orders }: { orders: PaperOrder[] }) {
  if (!orders.length) {
    return <p className="text-xs" style={{ color: "var(--text-muted)" }}>No paper orders yet.</p>;
  }
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead><tr><th>When</th><th>Side</th><th>Qty</th><th>Fill price</th><th>Notes</th></tr></thead>
        <tbody>
          {orders.map((o) => (
            <tr key={o.id}>
              <td className="text-xs" style={{ color: "var(--text-muted)" }}>{timeAgo(o.created_at)}</td>
              <td><span className={`badge ${o.side === "BUY" ? "badge-bullish" : "badge-bearish"}`}>{o.side}</span></td>
              <td className="tabular-nums">{o.quantity}</td>
              <td className="tabular-nums">{fmtUSD(o.fill_price)}</td>
              <td className="text-xs" style={{ color: "var(--text-secondary)" }}>{o.notes || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** "Not available" placeholder for a section when its data source doesn't have
 * anything for this symbol — scoped to just that section, never the whole page. */
function NotAvailable({ reason }: { reason?: string }) {
  return (
    <p className="text-xs" style={{ color: "var(--text-muted)" }}>
      {reason || "Not available."}
    </p>
  );
}

/** Technical scan across the default US watchlist — never auto-fires (it's a
 * ~24-symbol, ~10s scan); the user triggers it explicitly, same as AI Research
 * Notes elsewhere. Buy/Sell here only opens the paper-order dialog pre-filled
 * with the scanner's own live price/levels — it never places anything itself. */
function ScannerPanel({ onBuySell }: { onBuySell: (symbol: string, side: "BUY" | "SELL", price: number | null) => void }) {
  const [started, setStarted] = useState(false);
  const scanner = useApi(() => usMarketAPI.scanner(), [], { enabled: started });

  if (!started) {
    return (
      <button className="btn-primary text-xs" onClick={() => setStarted(true)}>
        <Zap size={13} /> Run US Scanner
      </button>
    );
  }
  if (scanner.loading) return <LoadingRows rows={5} />;
  if (scanner.error) return <ErrorState message={scanner.error} onRetry={scanner.reload} />;
  if (!scanner.data?.data_available) return <NotAvailable reason={scanner.data?.reason} />;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
          Scanned {scanner.data.scanned} default-watchlist symbols, {scanner.data.resolved} resolved — favorable setups first.
        </p>
        <button className="btn-ghost text-xs" onClick={scanner.reload}>Rescan</button>
      </div>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Symbol</th><th>Sector</th><th>LTP</th><th>Signal</th><th>RSI</th><th>Trend</th>
              <th>Entry zone</th><th>Stop</th><th>Target</th><th>R:R</th><th></th>
            </tr>
          </thead>
          <tbody>
            {(scanner.data.rows as USScannerRow[]).map((r) => (
              <tr key={r.symbol}>
                <td className="font-semibold">{r.symbol}</td>
                <td className="text-xs" style={{ color: "var(--text-muted)" }}>{r.sector}</td>
                <td className="tabular-nums">{fmtUSD(r.ltp)}</td>
                <td>{r.is_holding ? <span className="badge badge-info">{r.holding_action}</span> : <EntryBadge entry={r.entry} />}</td>
                <td className="tabular-nums text-xs">{r.rsi?.toFixed(1) ?? "—"}</td>
                <td className="text-xs">{r.trend || "—"}</td>
                <td className="tabular-nums text-xs">{r.entry_zone ? `${fmtUSD(r.entry_zone[0])}–${fmtUSD(r.entry_zone[1])}` : "—"}</td>
                <td className="tabular-nums text-xs text-bearish">{fmtUSD(r.stop_loss)}</td>
                <td className="tabular-nums text-xs text-bullish">{fmtUSD(r.target_1)}</td>
                <td className="tabular-nums text-xs">{r.risk_reward ? `1:${r.risk_reward}` : "—"}</td>
                <td>
                  <div className="flex gap-1">
                    <button className="btn-ghost text-xs" style={{ color: "var(--color-bullish)", padding: "4px 6px" }} onClick={() => onBuySell(r.symbol, "BUY", r.ltp)} title={`Paper buy ${r.symbol}`}>
                      <TrendingUp size={12} />
                    </button>
                    <button className="btn-ghost text-xs" style={{ color: "var(--color-bearish)", padding: "4px 6px" }} onClick={() => onBuySell(r.symbol, "SELL", r.ltp)} title={`Paper sell ${r.symbol}`}>
                      <TrendingDown size={12} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function USStockView() {
  const { usSymbol, setUsSymbol } = useAppStore();
  const [symbol, setSymbol] = useState("");
  const [order, setOrder] = useState<{ symbol: string; side: "BUY" | "SELL"; price: number | null } | null>(null);
  const [fxRate, setFxRate] = useState<number | null>(null);

  useEffect(() => {
    usMarketAPI.fxRate().then((res) => setFxRate(res.data.rate)).catch(() => setFxRate(null));
  }, []);

  // Picked up when the global top-bar search (or anywhere else) hands off a
  // symbol via the shared store — consumed once, then cleared, same pattern
  // as ReportView.tsx's reportSymbol.
  useEffect(() => {
    if (usSymbol) {
      setSymbol(usSymbol);
      setUsSymbol(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [usSymbol]);

  const universe = useApi(() => usMarketAPI.universe(), []);
  const analysis = useApi(() => usMarketAPI.analyze(symbol), [symbol], { enabled: !!symbol });
  const fundamentals = useApi(() => usMarketAPI.fundamentals(symbol), [symbol], { enabled: !!symbol });
  const news = useApi(() => usMarketAPI.news(symbol), [symbol], { enabled: !!symbol });
  const positions = useApi(() => paperTradingAPI.positions(), []);
  const orders = useApi(() => paperTradingAPI.orders(symbol || undefined), [symbol]);
  const trades = useApi(() => paperTradingAPI.trades(symbol || undefined), [symbol]);
  const summary = useApi(() => paperTradingAPI.summary(), []);

  const afterOrderPlaced = () => {
    setOrder(null);
    positions.reload();
    orders.reload();
    trades.reload();
    summary.reload();
  };

  const a = analysis.data;
  const s = a?.signal;
  const ee = s?.entry_exit;
  const q = a?.quote;
  const f = fundamentals.data;
  const newsItems: any[] = news.data?.news || [];

  return (
    <div className="space-y-5">
      <div className="flex items-start gap-3">
        <span className="badge mt-1" style={{ background: `${US_ACCENT}20`, color: US_ACCENT, flexShrink: 0 }}>US</span>
        <PageHeader
          title="Stocks"
          subtitle="Real US quotes/charts via Alpaca (once configured) and fundamentals via SEC EDGAR, plus paper trading and AI research — a separate report, distinct from the Indian Stock Report."
        />
      </div>

      {/* Search — any US ticker, not restricted to a fixed list (Alpaca/SEC
          resolve it; an invalid symbol just comes back "not available") */}
      <Card accent={US_ACCENT}>
        <SearchBox
          market="US"
          className="w-full md:max-w-md"
          placeholder="Enter any US ticker (e.g. AAPL, NFLX, DIS)…"
          onSelect={setSymbol}
        />
        <p className="text-[11px] mt-2" style={{ color: "var(--text-muted)" }}>
          Any valid NYSE/NASDAQ ticker works — type one and press Enter even if it's not in the suggestions below.
        </p>
      </Card>

      {/* US Scanner — technical scan across the default watchlist, favorable setups first */}
      <Card accent={US_ACCENT}>
        <SectionHeader icon={<Search size={16} />} title="US Scanner" subtitle="Finds favorable setups across the default watchlist — Buy/Sell opens a pre-filled paper order for you to confirm, nothing executes on its own" />
        <ScannerPanel onBuySell={(sym, side, price) => setOrder({ symbol: sym, side, price })} />
      </Card>

      {/* Popular picks / scanner's default watchlist */}
      <Card accent={US_ACCENT}>
        <SectionHeader title="Popular US Stocks" subtitle="Quick picks — also the Scanner's default watchlist. Search above for any other ticker." />
        {universe.loading ? (
          <LoadingRows rows={3} />
        ) : universe.error ? (
          <ErrorState message={universe.error} onRetry={universe.reload} />
        ) : (
          <div className="space-y-3">
            {Object.entries(universe.data?.universe || {}).map(([sector, symbols]) => (
              <div key={sector}>
                <p className="text-[11px] font-semibold uppercase mb-1.5" style={{ color: "var(--text-muted)" }}>{sector}</p>
                <div className="flex flex-wrap gap-2">
                  {symbols.map((sym) => (
                    <button key={sym} className={`chip ${sym === symbol ? "chip-active" : ""}`} onClick={() => setSymbol(sym)}>{sym}</button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {!symbol && (
        <Card>
          <EmptyState icon={<DollarSign size={28} />} title="No stock selected" description="Search any US ticker above, pick a popular one, or act on a Scanner result." />
        </Card>
      )}

      {symbol && (
        <>
          {/* Verdict strip */}
          <Card accent={US_ACCENT}>
            {analysis.loading ? (
              <LoadingRows rows={2} />
            ) : analysis.error ? (
              <ErrorState message={analysis.error} onRetry={analysis.reload} />
            ) : !a?.data_available ? (
              <div className="flex items-start gap-3">
                <AlertTriangle size={16} style={{ color: US_ACCENT, flexShrink: 0, marginTop: 1 }} />
                <div>
                  <p className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>{symbol} — live data not available</p>
                  <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>{a?.reason}</p>
                </div>
              </div>
            ) : (
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div className="flex items-center gap-3 min-w-0">
                  <div>
                    <div className="flex items-center gap-2">
                      <h2 className="text-xl font-bold" style={{ color: "var(--text-primary)" }}>{symbol}</h2>
                      <EntryBadge entry={s?.signal?.entry} />
                    </div>
                    <p className="text-[11px] mt-0.5" style={{ color: "var(--text-muted)" }}>
                      {a.sector} · {q?.feed_note || "Alpaca"} · {a.metadata?.candles_used} daily bars
                    </p>
                  </div>
                </div>
                {q?.data_available && (
                  <div className="text-right">
                    <p className="text-2xl font-bold tabular-nums" style={{ color: "var(--text-primary)" }}>{fmtUSD(q.ltp)}</p>
                    <p className={`text-sm font-semibold ${((q.change_pct ?? 0) >= 0) ? "text-bullish" : "text-bearish"}`}>
                      {q.change_pct != null ? fmtPct(q.change_pct) : "—"}
                    </p>
                  </div>
                )}
              </div>
            )}
          </Card>

          {/* Chart — real candles once Alpaca is configured */}
          <CandlestickChart symbol={symbol} market="US" />

          {a?.data_available && (
            <>
              {/* Technicals */}
              <Card>
                <SectionHeader icon={<BarChart3 size={16} />} title="Technicals" />
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <KeyValue label="RSI" value={s?.technical?.rsi?.toFixed?.(1) ?? "—"} />
                  <KeyValue label="ADX" value={s?.technical?.adx?.toFixed?.(1) ?? "—"} />
                  <KeyValue label="Trend" value={s?.technical?.trend ?? "—"} />
                  <KeyValue label="Volume ratio" value={s?.technical?.volume_ratio?.toFixed?.(2) ?? "—"} />
                </div>
              </Card>

              {/* Trade plan */}
              <Card>
                <SectionHeader icon={<Target size={16} />} title="Trade Plan" subtitle="Paper-trading sizing, default $10,000 capital" />
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <KeyValue label="Entry zone" value={ee?.entry_zone ? `${fmtUSD(ee.entry_zone[0])} – ${fmtUSD(ee.entry_zone[1])}` : "—"} />
                  <KeyValue label="Stop loss" value={fmtUSD(ee?.stop_loss)} valueColor="var(--color-bearish)" />
                  <KeyValue label="Target 1 / 2" value={`${fmtUSD(ee?.target_1)} / ${fmtUSD(ee?.target_2)}`} valueColor="var(--color-bullish)" />
                  <KeyValue label="Risk : reward" value={ee?.risk_reward ? `1 : ${ee.risk_reward}` : "—"} />
                </div>
              </Card>

              {/* Term outlook */}
              {a.predictions && (
                <Card>
                  <SectionHeader icon={<Target size={16} />} title="Term Outlook" subtitle="Does this work for short, medium or long-term holding?" />
                  <div className="table-scroll">
                    <table className="data-table">
                      <thead><tr><th>Term</th><th>Horizon</th><th>Verdict</th><th>Why</th></tr></thead>
                      <tbody>
                        {buildUSTermOutlook(a).map((row) => (
                          <tr key={row.term}>
                            <td className="font-semibold">{row.term}</td>
                            <td className="text-xs" style={{ color: "var(--text-muted)" }}>{row.horizon}</td>
                            <td><span className={`badge ${row.badgeClass}`}>{row.verdict}</span></td>
                            <td className="text-xs" style={{ color: "var(--text-secondary)" }}>{row.reason}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Card>
              )}

              {/* Multi-horizon model outlook */}
              {a.predictions && (
                <Card>
                  <SectionHeader title="Multi-Horizon Model Outlook" subtitle="Direction probabilities — not a price target" />
                  <div className="table-scroll">
                    <table className="data-table">
                      <thead><tr><th>Horizon</th><th>Up</th><th>Flat</th><th>Down</th><th>Expected return</th><th>Confidence</th></tr></thead>
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
                              <td className="text-xs">{p.confidence}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </Card>
              )}
            </>
          )}

          {/* Fundamentals — SEC EDGAR, always on regardless of Alpaca config */}
          <Card>
            <SectionHeader title="Fundamentals" subtitle="SEC EDGAR — official annual XBRL filings" />
            {fundamentals.loading ? <LoadingRows rows={3} /> : fundamentals.error ? (
              <ErrorState message={fundamentals.error} onRetry={fundamentals.reload} />
            ) : !f?.data_available ? (
              <NotAvailable reason={f?.reason} />
            ) : (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {(["revenue", "net_income", "total_assets", "total_liabilities", "operating_cash_flow", "eps_diluted"] as const).map((key) => {
                  const points = f[key] as { value: number; period: string }[] | null;
                  if (!points?.length) return null;
                  const label = { revenue: "Revenue", net_income: "Net income", total_assets: "Total assets", total_liabilities: "Total liabilities", operating_cash_flow: "Operating cash flow", eps_diluted: "EPS (diluted)" }[key];
                  return (
                    <div key={key} className="p-2 rounded-lg" style={{ background: "rgba(255,255,255,0.02)", border: "1px solid var(--border-subtle)" }}>
                      <p className="text-[10px]" style={{ color: "var(--text-muted)" }}>{label} ({points[0].period})</p>
                      <p className="text-sm font-bold tabular-nums" style={{ color: "var(--text-primary)" }}>
                        {key === "eps_diluted" ? `$${points[0].value}` : fmtUSD(points[0].value, 0)}
                      </p>
                    </div>
                  );
                })}
              </div>
            )}
          </Card>

          {/* News — Alpaca/Benzinga */}
          <Card>
            <SectionHeader icon={<Newspaper size={16} />} title="Recent News" subtitle="Alpaca (Benzinga-sourced)" />
            {news.loading ? <LoadingRows rows={3} /> : news.error ? (
              <ErrorState message={news.error} onRetry={news.reload} />
            ) : !news.data?.data_available ? (
              <NotAvailable reason={news.data?.reason} />
            ) : newsItems.length === 0 ? (
              <p className="text-xs" style={{ color: "var(--text-muted)" }}>No recent news for this stock.</p>
            ) : (
              <ul className="space-y-2">
                {newsItems.slice(0, 8).map((n: any, i: number) => (
                  <li key={`${n.url || n.heading || "news"}-${i}`} className="text-xs">
                    <a href={n.url} target="_blank" rel="noopener noreferrer" className="font-semibold hover:underline" style={{ color: "var(--text-primary)" }}>{n.heading}</a>
                    <span style={{ color: "var(--text-muted)" }}> · {timeAgo(n.published_at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {/* AI Research Notes */}
          <Card>
            <SectionHeader title="AI Research Notes" subtitle="Real-data analysis when available, general knowledge otherwise" />
            <USResearchNotes symbol={symbol} />
          </Card>

          {/* Paper Trading Desk */}
          <Card className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <SectionHeader title={`Paper Trading Desk — ${symbol}`} subtitle="Simulated only — no real brokerage call" />
              <div className="flex gap-2">
                <button className="btn-primary text-xs" style={{ background: "var(--color-bullish)" }} onClick={() => setOrder({ symbol, side: "BUY", price: q?.data_available ? q.ltp ?? null : null })}>
                  <TrendingUp size={13} /> Paper Buy
                </button>
                <button className="btn-secondary text-xs" style={{ color: "var(--color-bearish)" }} onClick={() => setOrder({ symbol, side: "SELL", price: q?.data_available ? q.ltp ?? null : null })}>
                  <TrendingDown size={13} /> Paper Sell
                </button>
              </div>
            </div>

            <div>
              <p className="text-[11px] font-bold uppercase mb-2" style={{ color: "var(--text-muted)" }}>Positions</p>
              {positions.loading ? <LoadingRows rows={2} /> : positions.error ? (
                <ErrorState message={positions.error} onRetry={positions.reload} />
              ) : (
                <PositionsTable positions={(positions.data?.positions || []).filter((p) => p.symbol === symbol)} fxRate={fxRate} />
              )}
            </div>

            <div>
              <p className="text-[11px] font-bold uppercase mb-2" style={{ color: "var(--text-muted)" }}>Order ledger</p>
              {orders.loading ? <LoadingRows rows={3} /> : orders.error ? (
                <ErrorState message={orders.error} onRetry={orders.reload} />
              ) : (
                <OrdersTable orders={orders.data?.orders || []} />
              )}
            </div>
          </Card>

          <Card>
            <SectionHeader icon={<Receipt size={16} />} title={`Trade History & Taxes — ${symbol}`} subtitle="Every closed buy/sell pair, FIFO-matched, with holding period and estimated tax" />
            {trades.loading ? <LoadingRows rows={3} /> : trades.error ? (
              <ErrorState message={trades.error} onRetry={trades.reload} />
            ) : (
              <TradesTable trades={trades.data?.trades || []} fxRate={fxRate} />
            )}
          </Card>
        </>
      )}

      {/* Overall paper P&L and estimated tax — all symbols, always visible */}
      {summary.loading ? (
        <Card><LoadingRows rows={2} /></Card>
      ) : summary.error ? (
        <ErrorState message={summary.error} onRetry={summary.reload} />
      ) : summary.data ? (
        <TaxSummaryStrip summary={summary.data} fxRate={fxRate} />
      ) : null}

      {order && (
        <PaperOrderDialog
          open={!!order}
          onClose={() => setOrder(null)}
          symbol={order.symbol}
          side={order.side}
          defaultPrice={order.price}
          onPlaced={afterOrderPlaced}
        />
      )}
    </div>
  );
}
