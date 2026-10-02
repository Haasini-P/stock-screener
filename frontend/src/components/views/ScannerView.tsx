"use client";

import { Fragment, useMemo, useRef, useState } from "react";
import { ArrowDown, ArrowUp, BellPlus, ChevronDown, ChevronUp, Download, Plus, RotateCcw, Search, Sparkles, TrendingDown, TrendingUp, X } from "lucide-react";
import { marketAPI, MAX_BATCH_SYMBOLS, watchlistAPI, WatchlistEntry, WatchlistTerm } from "@/lib/api";
import { useAppStore } from "@/lib/store";
import { useApi } from "@/lib/useApi";
import { fmtDate, fmtINR, fmtNum, fmtPct, humanize, toneColor } from "@/lib/format";
import { buildRecommendation } from "@/lib/verdict";
import AICommentary from "../AICommentary";
import AlertDialog from "../AlertDialog";
import BatchAICommentary from "../BatchAICommentary";
import OrderTicketDialog, { OrderDefaults } from "../OrderTicketDialog";
import WatchlistAddDialog from "../WatchlistAddDialog";
import { BucketChips, Card, EmptyState, EntryBadge, ErrorState, LoadingRows, PageHeader, RefreshButton, StockLink } from "../ui";

const TERM_FILTERS: { value: "" | WatchlistTerm; label: string }[] = [
  { value: "", label: "All terms" },
  { value: "short", label: "Short term" },
  { value: "mid", label: "Mid term" },
  { value: "long", label: "Long term" },
];

interface Filters {
  q: string;
  sector: string;
  bucket: string;
  entry: string;
  min_rsi: string;
  max_rsi: string;
  min_volume_ratio: string;
  min_change: string;
  max_change: string;
  sort_by: string;
  order: "asc" | "desc";
}

const EMPTY: Filters = {
  q: "", sector: "", bucket: "", entry: "", min_rsi: "", max_rsi: "",
  min_volume_ratio: "", min_change: "", max_change: "", sort_by: "change_pct", order: "desc",
};

const PRESETS: { label: string; filters: Partial<Filters> }[] = [
  { label: "Momentum breakouts", filters: { bucket: "momentum_breakout" } },
  { label: "Breakout retests", filters: { bucket: "breakout_retest" } },
  { label: "Quality pullbacks", filters: { bucket: "quality_pullback" } },
  { label: "Volume shockers (≥2x)", filters: { min_volume_ratio: "2", sort_by: "volume_ratio" } },
  { label: "Oversold (RSI < 30)", filters: { max_rsi: "30", sort_by: "rsi", order: "asc" } },
  { label: "Overbought (RSI > 70)", filters: { min_rsi: "70", sort_by: "rsi" } },
  { label: "Near 52-week high", filters: { sort_by: "dist_52w_high" } },
  { label: "Top gainers", filters: { min_change: "0", sort_by: "change_pct" } },
  { label: "Top losers", filters: { max_change: "0", sort_by: "change_pct", order: "asc" } },
];

// "Trade" and "Why" are deliberately the 2nd/3rd columns (not the last) so the
// Buy/Sell actions are visible without scrolling this wide table horizontally.
const COLUMNS: { key: string; label: string; sortable?: boolean }[] = [
  { key: "symbol", label: "Stock", sortable: true },
  { key: "trade", label: "Trade" },
  { key: "why", label: "Why" },
  { key: "entry", label: "Signal" },
  { key: "ltp", label: "LTP", sortable: true },
  { key: "change_pct", label: "Day %", sortable: true },
  { key: "return_5d", label: "5D %", sortable: true },
  { key: "return_20d", label: "20D %", sortable: true },
  { key: "volume_ratio", label: "Vol ×", sortable: true },
  { key: "rsi", label: "RSI", sortable: true },
  { key: "adx", label: "ADX", sortable: true },
  { key: "dist_52w_high", label: "From 52W H", sortable: true },
  { key: "trend", label: "Trend" },
  { key: "probability_up", label: "P(up)", sortable: true },
  { key: "buckets", label: "Setups" },
  { key: "term", label: "Term" },
  { key: "added", label: "Added" },
];

function toParams(f: Filters, refresh = false) {
  const p: Record<string, string | boolean> = { sort_by: f.sort_by, order: f.order };
  for (const k of ["q", "sector", "bucket", "entry", "min_rsi", "max_rsi", "min_volume_ratio", "min_change", "max_change"] as const) {
    if (f[k] !== "") p[k] = f[k];
  }
  if (refresh) p.refresh = true;
  return p;
}

function TermCell({
  symbol, term, onSetTerm, onRemove,
}: {
  symbol: string;
  term?: WatchlistTerm;
  onSetTerm: (symbol: string, term: WatchlistTerm) => void;
  onRemove?: (symbol: string) => void;
}) {
  return (
    <div className="flex items-center gap-1">
      <select
        className="input text-[11px]"
        style={{ padding: "2px 4px", width: "auto" }}
        value={term || ""}
        onChange={(e) => e.target.value && onSetTerm(symbol, e.target.value as WatchlistTerm)}
      >
        <option value="" disabled>{term ? humanize(term) : "Track…"}</option>
        <option value="short">Short</option>
        <option value="mid">Mid</option>
        <option value="long">Long</option>
      </select>
      {term && onRemove && (
        <button className="btn-ghost" style={{ padding: 2 }} onClick={() => onRemove(symbol)} title="Remove from watchlist">
          <X size={11} />
        </button>
      )}
    </div>
  );
}

function ExtraWatchlistRow({
  symbol, item, onBuySell, onSetTerm, onRemove, onAlert,
}: {
  symbol: string;
  item: WatchlistEntry;
  onBuySell: (row: any, side: "BUY" | "SELL") => void;
  onSetTerm: (symbol: string, term: WatchlistTerm) => void;
  onRemove: (symbol: string) => void;
  onAlert: (symbol: string) => void;
}) {
  const quote = useApi(() => marketAPI.quote(symbol), [symbol]);
  const q = quote.data;
  return (
    <tr style={{ opacity: 0.8 }}>
      <td>
        <StockLink symbol={symbol} />
        <div className="text-[10px]" style={{ color: "var(--text-muted)" }}>Not in current scan results</div>
      </td>
      <td>
        <div className="flex gap-1">
          <button className="btn-secondary text-xs" style={{ padding: "4px 8px", color: "var(--color-bullish)" }} onClick={() => onBuySell({ symbol, ltp: q?.ltp }, "BUY")}>
            <TrendingUp size={13} /> Buy
          </button>
          <button className="btn-secondary text-xs" style={{ padding: "4px 8px", color: "var(--color-bearish)" }} onClick={() => onBuySell({ symbol, ltp: q?.ltp }, "SELL")}>
            <TrendingDown size={13} /> Sell
          </button>
          <button className="btn-ghost text-xs" style={{ padding: "4px 6px" }} onClick={() => onAlert(symbol)} title={`Notify me when ${symbol} becomes a BUY signal`}>
            <BellPlus size={13} />
          </button>
        </div>
      </td>
      <td className="text-[10px]" style={{ color: "var(--text-muted)" }}>No signal data</td>
      <td>—</td>
      <td className="tabular-nums">{q ? fmtINR(q.ltp) : quote.loading ? "…" : "—"}</td>
      <td className="tabular-nums" style={{ color: toneColor(q?.change_pct) }}>{q ? fmtPct(q.change_pct) : "—"}</td>
      <td colSpan={9} className="text-[10px]" style={{ color: "var(--text-muted)" }}>
        Outside the live scan universe or current filters — no technicals computed for this symbol.
      </td>
      <td><TermCell symbol={symbol} term={item.term} onSetTerm={onSetTerm} onRemove={onRemove} /></td>
      <td className="text-xs whitespace-nowrap">{fmtDate(item.added_at)}</td>
    </tr>
  );
}

function exportCsv(rows: any[]) {
  const cols = ["symbol", "name", "sector", "ltp", "change_pct", "return_5d", "return_20d", "volume_ratio", "rsi", "adx",
    "dist_52w_high", "trend", "entry", "probability_up", "stop_loss", "target_1", "target_2", "buckets"];
  const esc = (v: any) => {
    const s = Array.isArray(v) ? v.join("|") : v == null ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const csv = [cols.join(","), ...rows.map((r) => cols.map((c) => esc(r[c])).join(","))].join("\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = `stockmind-scan-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export default function ScannerView() {
  const { toast } = useAppStore();
  const [filters, setFilters] = useState<Filters>(EMPTY);
  const [applied, setApplied] = useState<Filters>(EMPTY);
  const [rescans, setRescans] = useState(0);
  const refreshNext = useRef(false); // force a server-side rebuild on the next fetch only
  const [expanded, setExpanded] = useState<string | null>(null);
  const [order, setOrder] = useState<{ symbol: string; side: "BUY" | "SELL"; defaults: OrderDefaults } | null>(null);
  const [batchSymbols, setBatchSymbols] = useState<string[] | null>(null);
  const [termFilter, setTermFilter] = useState<"" | WatchlistTerm>("");
  const [addOpen, setAddOpen] = useState(false);
  const [alertSymbol, setAlertSymbol] = useState<string | null>(null);

  const watchlist = useApi(() => watchlistAPI.list(), []);
  const watchlistBySymbol = useMemo(() => {
    const m = new Map<string, WatchlistEntry>();
    for (const item of watchlist.data?.items || []) m.set(item.symbol, item);
    return m;
  }, [watchlist.data]);

  const setTerm = async (symbol: string, term: WatchlistTerm) => {
    try {
      await watchlistAPI.add(symbol, term);
      watchlist.reload();
    } catch (err: any) {
      toast(err?.response?.data?.detail || "Could not update watchlist.", "error");
    }
  };
  const removeFromWatchlist = async (symbol: string) => {
    try {
      await watchlistAPI.remove(symbol);
      watchlist.reload();
    } catch (err: any) {
      toast(err?.response?.data?.detail || "Could not remove from watchlist.", "error");
    }
  };

  const openOrder = (row: any, side: "BUY" | "SELL") =>
    setOrder({
      symbol: row.symbol,
      side,
      defaults: {
        quantity: row.quantity || 1,
        price: row.entry_zone?.[side === "BUY" ? 1 : 0] ?? row.ltp,
        product: "DELIVERY",
        target: side === "BUY" ? row.target_1 : undefined,
        stopLoss: side === "BUY" ? row.stop_loss : undefined,
      },
    });

  const scan = useApi(() => {
    const refresh = refreshNext.current;
    refreshNext.current = false;
    return marketAPI.scanner(toParams(applied, refresh));
  }, [applied, rescans]);
  const options = scan.data?.options;
  const scanRows: any[] = useMemo(() => scan.data?.results || [], [scan.data]);
  const rows = useMemo(
    () => (termFilter ? scanRows.filter((r) => watchlistBySymbol.get(r.symbol)?.term === termFilter) : scanRows),
    [scanRows, termFilter, watchlistBySymbol]
  );
  // Manually-tracked symbols that don't currently pass the live screen at all —
  // still shown (with live quote only, no technicals) so "add manually" actually works.
  const extraSymbols = useMemo(() => {
    const scanned = new Set(scanRows.map((r) => r.symbol));
    return (watchlist.data?.items || [])
      .filter((i) => !scanned.has(i.symbol) && (!termFilter || i.term === termFilter))
      .map((i) => i.symbol);
  }, [scanRows, watchlist.data, termFilter]);

  const set = (patch: Partial<Filters>) => setFilters((f) => ({ ...f, ...patch }));
  const apply = (f: Filters = filters) => setApplied(f);
  const preset = (p: Partial<Filters>) => {
    const next = { ...EMPTY, ...p };
    setFilters(next);
    apply(next);
  };
  const sort = (key: string) => {
    const next: Filters = {
      ...applied,
      sort_by: key,
      order: applied.sort_by === key && applied.order === "desc" ? "asc" : "desc",
    };
    setFilters(next);
    apply(next);
  };

  const activePreset = useMemo(
    () => PRESETS.find((p) => JSON.stringify({ ...EMPTY, ...p.filters }) === JSON.stringify(applied))?.label,
    [applied]
  );

  return (
    <div>
      <PageHeader
        title="Market Scanner"
        subtitle={
          scan.data
            ? `${scan.data.metadata.analyzed} of ${scan.data.metadata.universe_size} stocks analyzed across ${options?.sectors.length} approved sectors · regime ${scan.data.metadata.regime}`
            : "Live technical scan of the approved sector universe"
        }
        actions={
          <>
            <button className="btn-secondary text-xs" style={{ padding: "6px 12px" }} onClick={() => setAddOpen(true)}>
              <Plus size={13} /> Add to watchlist
            </button>
            <button
              className="btn-secondary text-xs"
              style={{ padding: "6px 12px" }}
              onClick={() =>
                rows.length
                  ? setBatchSymbols(rows.slice(0, MAX_BATCH_SYMBOLS).map((r) => r.symbol))
                  : toast("Nothing to analyze", "info")
              }
              title={`AI quick scan of the top ${MAX_BATCH_SYMBOLS} currently filtered/sorted stocks`}
            >
              <Sparkles size={13} /> Batch AI take
            </button>
            <button className="btn-secondary text-xs" style={{ padding: "6px 12px" }} onClick={() => (rows.length ? exportCsv(rows) : toast("Nothing to export", "info"))}>
              <Download size={13} /> Export CSV
            </button>
            <RefreshButton
              onClick={() => {
                refreshNext.current = true;
                setRescans((n) => n + 1);
              }}
              busy={scan.loading || scan.refreshing}
              label="Rescan"
              updatedAt={scan.updatedAt}
            />
          </>
        }
      />

      {/* Presets */}
      <div className="flex gap-2 overflow-x-auto pb-2 mb-3">
        {PRESETS.map((p) => (
          <button key={p.label} className={`chip ${activePreset === p.label ? "chip-active" : ""}`} onClick={() => preset(p.filters)}>
            {p.label}
          </button>
        ))}
      </div>

      {/* Watchlist term segregation */}
      <div className="flex gap-2 overflow-x-auto pb-2 mb-3">
        {TERM_FILTERS.map((t) => {
          const count = t.value ? (watchlist.data?.items || []).filter((i) => i.term === t.value).length : watchlist.data?.items.length || 0;
          return (
            <button key={t.value || "all"} className={`chip ${termFilter === t.value ? "chip-active" : ""}`} onClick={() => setTermFilter(t.value)}>
              {t.label} {count > 0 && <span style={{ opacity: 0.6 }}>({count})</span>}
            </button>
          );
        })}
      </div>

      {/* Filters */}
      <Card className="mb-5">
        <form
          className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-3 items-end"
          onSubmit={(e) => {
            e.preventDefault();
            apply();
          }}
        >
          <div className="col-span-2">
            <label className="field-label" htmlFor="scan-q">Search</label>
            <input id="scan-q" className="input" placeholder="Symbol or name" value={filters.q} onChange={(e) => set({ q: e.target.value })} />
          </div>
          <div>
            <label className="field-label" htmlFor="scan-sector">Sector</label>
            <select id="scan-sector" className="input" value={filters.sector} onChange={(e) => set({ sector: e.target.value })}>
              <option value="">All sectors</option>
              {options?.sectors.map((s: string) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label className="field-label" htmlFor="scan-bucket">Setup</label>
            <select id="scan-bucket" className="input" value={filters.bucket} onChange={(e) => set({ bucket: e.target.value })}>
              <option value="">Any setup</option>
              {options?.buckets.map((b: string) => <option key={b} value={b}>{humanize(b)}</option>)}
            </select>
          </div>
          <div>
            <label className="field-label" htmlFor="scan-entry">Signal</label>
            <select id="scan-entry" className="input" value={filters.entry} onChange={(e) => set({ entry: e.target.value })}>
              <option value="">Any signal</option>
              {options?.entries.map((s: string) => <option key={s} value={s}>{humanize(s.toLowerCase())}</option>)}
            </select>
          </div>
          <div>
            <label className="field-label">RSI range</label>
            <div className="flex gap-1">
              <input className="input" type="number" min={0} max={100} placeholder="0" value={filters.min_rsi} onChange={(e) => set({ min_rsi: e.target.value })} aria-label="Minimum RSI" />
              <input className="input" type="number" min={0} max={100} placeholder="100" value={filters.max_rsi} onChange={(e) => set({ max_rsi: e.target.value })} aria-label="Maximum RSI" />
            </div>
          </div>
          <div>
            <label className="field-label" htmlFor="scan-vol">Min vol ×</label>
            <input id="scan-vol" className="input" type="number" step="0.1" min={0} placeholder="0" value={filters.min_volume_ratio} onChange={(e) => set({ min_volume_ratio: e.target.value })} />
          </div>
          <div>
            <label className="field-label">Day % range</label>
            <div className="flex gap-1">
              <input className="input" type="number" step="0.1" placeholder="min" value={filters.min_change} onChange={(e) => set({ min_change: e.target.value })} aria-label="Minimum day change" />
              <input className="input" type="number" step="0.1" placeholder="max" value={filters.max_change} onChange={(e) => set({ max_change: e.target.value })} aria-label="Maximum day change" />
            </div>
          </div>
          <div className="col-span-2 md:col-span-4 xl:col-span-8 flex gap-2 justify-end">
            <button type="button" className="btn-ghost text-xs" onClick={() => preset({})}>
              <RotateCcw size={13} /> Reset
            </button>
            <button type="submit" className="btn-primary text-xs" style={{ padding: "8px 16px" }}>
              <Search size={13} /> Apply filters
            </button>
          </div>
        </form>
      </Card>

      {/* Results */}
      <Card padded={false}>
        <div className="px-5 py-3 border-b text-xs flex justify-between" style={{ borderColor: "var(--border-subtle)", color: "var(--text-muted)" }}>
          <span>
            {scan.data
              ? termFilter
                ? `${rows.length + extraSymbols.length} ${TERM_FILTERS.find((t) => t.value === termFilter)?.label.toLowerCase()} stocks`
                : `${scan.data.total} matching stocks`
              : "Scanning…"}
          </span>
          <span>Click a column header to sort · click a stock for full analysis</span>
        </div>
        <div className="p-2">
          {scan.loading ? (
            <div className="p-3"><LoadingRows rows={8} /></div>
          ) : scan.error ? (
            <div className="p-3"><ErrorState message={scan.error} onRetry={scan.reload} /></div>
          ) : rows.length === 0 && extraSymbols.length === 0 ? (
            <div className="p-3">
              <EmptyState title="No stocks match these filters" description="Try widening the RSI or change range, or reset the filters." action={<button className="btn-secondary text-xs" onClick={() => preset({})}>Reset filters</button>} />
            </div>
          ) : (
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    {COLUMNS.map((c) => (
                      <th
                        key={c.key}
                        className={c.sortable ? "sortable" : ""}
                        onClick={c.sortable ? () => sort(c.key) : undefined}
                        aria-sort={applied.sort_by === c.key ? (applied.order === "asc" ? "ascending" : "descending") : undefined}
                      >
                        <span className="inline-flex items-center gap-1">
                          {c.label}
                          {applied.sort_by === c.key && (applied.order === "asc" ? <ArrowUp size={11} /> : <ArrowDown size={11} />)}
                        </span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <Fragment key={r.symbol}>
                      <tr>
                        <td>
                          <StockLink symbol={r.symbol} />
                          <div className="text-[10px]" style={{ color: "var(--text-muted)" }}>{r.sector}</div>
                        </td>
                        <td>
                          <div className="flex gap-1">
                            <button
                              className="btn-secondary text-xs"
                              style={{ padding: "4px 8px", color: "var(--color-bullish)" }}
                              onClick={() => openOrder(r, "BUY")}
                              title={`Buy ${r.symbol}`}
                            >
                              <TrendingUp size={13} /> Buy
                            </button>
                            <button
                              className="btn-secondary text-xs"
                              style={{ padding: "4px 8px", color: "var(--color-bearish)" }}
                              onClick={() => openOrder(r, "SELL")}
                              title={`Sell ${r.symbol}`}
                            >
                              <TrendingDown size={13} /> Sell
                            </button>
                            <button
                              className="btn-ghost text-xs"
                              style={{ padding: "4px 6px" }}
                              onClick={() => setAlertSymbol(r.symbol)}
                              title={`Notify me when ${r.symbol} becomes a BUY signal`}
                            >
                              <BellPlus size={13} />
                            </button>
                          </div>
                        </td>
                        <td>
                          <button
                            className="btn-ghost text-xs"
                            style={{ padding: "4px 8px" }}
                            onClick={() => setExpanded(expanded === r.symbol ? null : r.symbol)}
                          >
                            Why {expanded === r.symbol ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                          </button>
                        </td>
                        <td><EntryBadge entry={r.entry} /></td>
                        <td className="tabular-nums">{fmtINR(r.ltp)}</td>
                        <td className="tabular-nums" style={{ color: toneColor(r.change_pct) }}>{fmtPct(r.change_pct)}</td>
                        <td className="tabular-nums" style={{ color: toneColor(r.return_5d) }}>{fmtPct(r.return_5d)}</td>
                        <td className="tabular-nums" style={{ color: toneColor(r.return_20d) }}>{fmtPct(r.return_20d)}</td>
                        <td className="tabular-nums" style={{ color: r.volume_ratio >= 2 ? "var(--color-neutral)" : undefined }}>{fmtNum(r.volume_ratio)}</td>
                        <td className="tabular-nums" style={{ color: r.rsi > 70 ? "var(--color-bearish)" : r.rsi < 30 ? "var(--color-bullish)" : undefined }}>{fmtNum(r.rsi, 1)}</td>
                        <td className="tabular-nums">{fmtNum(r.adx, 1)}</td>
                        <td className="tabular-nums">{fmtPct(r.dist_52w_high)}</td>
                        <td className="text-xs whitespace-nowrap">{r.trend}</td>
                        <td className="tabular-nums">{r.probability_up != null ? `${(r.probability_up * 100).toFixed(0)}%` : "—"}</td>
                        <td><BucketChips buckets={r.buckets} /></td>
                        <td>
                          <TermCell
                            symbol={r.symbol}
                            term={watchlistBySymbol.get(r.symbol)?.term}
                            onSetTerm={setTerm}
                            onRemove={watchlistBySymbol.has(r.symbol) ? removeFromWatchlist : undefined}
                          />
                        </td>
                        <td className="text-xs whitespace-nowrap">{fmtDate(watchlistBySymbol.get(r.symbol)?.added_at)}</td>
                      </tr>
                      {expanded === r.symbol && (
                        <tr>
                          <td colSpan={COLUMNS.length} className="text-xs" style={{ background: "rgba(99, 102, 241, 0.04)" }}>
                            <div className="py-2 px-1 space-y-2">
                              <p style={{ color: "var(--text-primary)" }}>{buildRecommendation(r)}</p>
                              <div className="flex flex-wrap gap-4 text-[11px]" style={{ color: "var(--text-muted)" }}>
                                <span>Entry zone: {r.entry_zone ? `${fmtNum(r.entry_zone[0])} – ${fmtNum(r.entry_zone[1])}` : "—"}</span>
                                <span>Stop loss: {fmtNum(r.stop_loss)}</span>
                                <span>Targets: {fmtNum(r.target_1)} / {fmtNum(r.target_2)}</span>
                                <span>R:R: {r.risk_reward ? `1:${r.risk_reward}` : "—"}</span>
                              </div>
                              <AICommentary symbol={r.symbol} />
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                  {extraSymbols.map((symbol) => {
                    const item = watchlistBySymbol.get(symbol);
                    if (!item) return null;
                    return (
                      <ExtraWatchlistRow key={symbol} symbol={symbol} item={item} onBuySell={openOrder} onSetTerm={setTerm} onRemove={removeFromWatchlist} onAlert={setAlertSymbol} />
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Card>

      {order && (
        <OrderTicketDialog
          open={!!order}
          onClose={() => setOrder(null)}
          symbol={order.symbol}
          side={order.side}
          defaults={order.defaults}
        />
      )}

      {batchSymbols && (
        <BatchAICommentary open={!!batchSymbols} onClose={() => setBatchSymbols(null)} symbols={batchSymbols} />
      )}

      <WatchlistAddDialog open={addOpen} onClose={() => setAddOpen(false)} onAdded={() => watchlist.reload()} />

      <AlertDialog open={!!alertSymbol} onClose={() => setAlertSymbol(null)} symbol={alertSymbol || ""} defaultType="signal_buy" />
    </div>
  );
}
