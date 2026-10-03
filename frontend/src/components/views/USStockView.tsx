"use client";

/**
 * StockMind AI — US Stocks (Paper Trading & Research)
 *
 * Deliberately NOT a clone of ReportView.tsx. Upstox's public API has no
 * individual US equity data (quotes/candles/fundamentals) — only Indian
 * exchanges plus a few global index quotes — so a page built around live
 * numbers would be empty everywhere. Instead this is three honest panels:
 *   1. Universe Browser — pick a symbol from the small approved list (no live
 *      instrument search exists for US stocks yet).
 *   2. Paper Trading Desk — simulated BUY/SELL (you enter the fill price;
 *      there's no live quote to execute against) and the resulting ledger/positions.
 *   3. AI Research Notes — the model's own general knowledge about the company,
 *      clearly labeled GENERAL_KNOWLEDGE (not live/verified data).
 */

import { useState } from "react";
import { AlertTriangle, DollarSign, Sparkles, TrendingDown, TrendingUp } from "lucide-react";
import { PaperOrder, PaperPosition, USResearchResult, errorMessage, paperTradingAPI, usMarketAPI } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { fmtUSD, timeAgo } from "@/lib/format";
import PaperOrderDialog from "../PaperOrderDialog";
import MarkdownContent from "../MarkdownContent";
import { Card, EmptyState, ErrorState, LoadingRows, PageHeader, SectionHeader } from "../ui";

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
      <button className="btn-ghost text-xs" onClick={run} title={`General-knowledge research notes on ${symbol}`}>
        <Sparkles size={12} /> AI Research Notes
      </button>
    );
  }

  return (
    <div className="p-3 rounded-lg" style={{ background: "rgba(245, 158, 11, 0.06)", border: "1px solid rgba(245, 158, 11, 0.25)" }}>
      <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wide" style={{ color: "var(--color-neutral-warn, #f59e0b)" }}>
        <AlertTriangle size={11} /> General knowledge — not live or verified data
      </div>
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

function PositionsTable({ positions }: { positions: PaperPosition[] }) {
  if (!positions.length) {
    return <p className="text-xs" style={{ color: "var(--text-muted)" }}>No paper positions yet.</p>;
  }
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead><tr><th>Symbol</th><th>Qty</th><th>Avg cost</th><th>Realized P&L</th></tr></thead>
        <tbody>
          {positions.map((p) => (
            <tr key={p.symbol}>
              <td className="font-semibold">{p.symbol}</td>
              <td className="tabular-nums">{p.quantity}</td>
              <td className="tabular-nums">{fmtUSD(p.avg_cost)}</td>
              <td className={`tabular-nums ${p.realized_pnl > 0 ? "text-bullish" : p.realized_pnl < 0 ? "text-bearish" : ""}`}>
                {fmtUSD(p.realized_pnl)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
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

export default function USStockView() {
  const [symbol, setSymbol] = useState("");
  const [order, setOrder] = useState<{ side: "BUY" | "SELL" } | null>(null);

  const universe = useApi(() => usMarketAPI.universe(), []);
  const positions = useApi(() => paperTradingAPI.positions(), []);
  const orders = useApi(() => paperTradingAPI.orders(symbol || undefined), [symbol]);

  const afterOrderPlaced = () => {
    setOrder(null);
    positions.reload();
    orders.reload();
  };

  return (
    <div className="space-y-5">
      <PageHeader
        title="US Stocks"
        subtitle="Paper trading and research for US equities — Upstox has no live US market data yet, so this is simulated trading plus the AI's own general knowledge, not a live report."
      />

      <div className="glass-card-static p-3 flex items-start gap-3" style={{ borderLeft: "3px solid var(--color-info)" }}>
        <AlertTriangle size={16} style={{ color: "var(--color-info)", flexShrink: 0, marginTop: 1 }} />
        <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
          <strong style={{ color: "var(--text-secondary)" }}>NO LIVE US MARKET DATA.</strong>{" "}
          Upstox&apos;s public API only covers Indian exchanges plus a few global index quotes — no
          individual US stock prices, charts or fundamentals. Orders here are simulated (you enter
          the fill price yourself) and AI notes are the model&apos;s own general knowledge, clearly
          labeled as such — never treat either as live market data.
        </p>
      </div>

      {/* Universe browser */}
      <Card>
        <SectionHeader title="Approved US Stocks" subtitle="No live instrument search yet — pick from this list" />
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
                  {symbols.map((s) => (
                    <button key={s} className={`chip ${s === symbol ? "chip-active" : ""}`} onClick={() => setSymbol(s)}>{s}</button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {!symbol && (
        <Card>
          <EmptyState icon={<DollarSign size={28} />} title="No stock selected" description="Pick a symbol above to open its paper trading desk and AI research notes." />
        </Card>
      )}

      {symbol && (
        <>
          <Card className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <SectionHeader title={`Paper Trading Desk — ${symbol}`} subtitle="Simulated only — no real brokerage call" />
              <div className="flex gap-2">
                <button className="btn-primary text-xs" style={{ background: "var(--color-bullish)" }} onClick={() => setOrder({ side: "BUY" })}>
                  <TrendingUp size={13} /> Paper Buy
                </button>
                <button className="btn-secondary text-xs" style={{ color: "var(--color-bearish)" }} onClick={() => setOrder({ side: "SELL" })}>
                  <TrendingDown size={13} /> Paper Sell
                </button>
              </div>
            </div>

            <div>
              <p className="text-[11px] font-bold uppercase mb-2" style={{ color: "var(--text-muted)" }}>Positions</p>
              {positions.loading ? <LoadingRows rows={2} /> : positions.error ? (
                <ErrorState message={positions.error} onRetry={positions.reload} />
              ) : (
                <PositionsTable positions={(positions.data?.positions || []).filter((p) => p.symbol === symbol)} />
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
            <SectionHeader title="AI Research Notes" subtitle="The model's own general knowledge — not live data" />
            <USResearchNotes symbol={symbol} />
          </Card>
        </>
      )}

      {order && symbol && (
        <PaperOrderDialog open={!!order} onClose={() => setOrder(null)} symbol={symbol} side={order.side} onPlaced={afterOrderPlaced} />
      )}
    </div>
  );
}
