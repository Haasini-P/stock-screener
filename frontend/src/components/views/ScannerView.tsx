"use client";

import { useMemo, useRef, useState } from "react";
import { ArrowDown, ArrowUp, Download, RotateCcw, Search } from "lucide-react";
import { marketAPI } from "@/lib/api";
import { useAppStore } from "@/lib/store";
import { useApi } from "@/lib/useApi";
import { fmtINR, fmtNum, fmtPct, humanize, toneColor } from "@/lib/format";
import { BucketChips, Card, EmptyState, EntryBadge, ErrorState, LoadingRows, PageHeader, RefreshButton, StockLink } from "../ui";

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

const COLUMNS: { key: string; label: string; sortable?: boolean }[] = [
  { key: "symbol", label: "Stock", sortable: true },
  { key: "ltp", label: "LTP", sortable: true },
  { key: "change_pct", label: "Day %", sortable: true },
  { key: "return_5d", label: "5D %", sortable: true },
  { key: "return_20d", label: "20D %", sortable: true },
  { key: "volume_ratio", label: "Vol ×", sortable: true },
  { key: "rsi", label: "RSI", sortable: true },
  { key: "adx", label: "ADX", sortable: true },
  { key: "dist_52w_high", label: "From 52W H", sortable: true },
  { key: "trend", label: "Trend" },
  { key: "entry", label: "Signal" },
  { key: "probability_up", label: "P(up)", sortable: true },
  { key: "buckets", label: "Setups" },
];

function toParams(f: Filters, refresh = false) {
  const p: Record<string, string | boolean> = { sort_by: f.sort_by, order: f.order };
  for (const k of ["q", "sector", "bucket", "entry", "min_rsi", "max_rsi", "min_volume_ratio", "min_change", "max_change"] as const) {
    if (f[k] !== "") p[k] = f[k];
  }
  if (refresh) p.refresh = true;
  return p;
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

  const scan = useApi(() => {
    const refresh = refreshNext.current;
    refreshNext.current = false;
    return marketAPI.scanner(toParams(applied, refresh));
  }, [applied, rescans]);
  const options = scan.data?.options;
  const rows: any[] = scan.data?.results || [];

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
          <span>{scan.data ? `${scan.data.total} matching stocks` : "Scanning…"}</span>
          <span>Click a column header to sort · click a stock for full analysis</span>
        </div>
        <div className="p-2">
          {scan.loading ? (
            <div className="p-3"><LoadingRows rows={8} /></div>
          ) : scan.error ? (
            <div className="p-3"><ErrorState message={scan.error} onRetry={scan.reload} /></div>
          ) : rows.length === 0 ? (
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
                    <tr key={r.symbol}>
                      <td>
                        <StockLink symbol={r.symbol} />
                        <div className="text-[10px]" style={{ color: "var(--text-muted)" }}>{r.sector}</div>
                      </td>
                      <td className="tabular-nums">{fmtINR(r.ltp)}</td>
                      <td className="tabular-nums" style={{ color: toneColor(r.change_pct) }}>{fmtPct(r.change_pct)}</td>
                      <td className="tabular-nums" style={{ color: toneColor(r.return_5d) }}>{fmtPct(r.return_5d)}</td>
                      <td className="tabular-nums" style={{ color: toneColor(r.return_20d) }}>{fmtPct(r.return_20d)}</td>
                      <td className="tabular-nums" style={{ color: r.volume_ratio >= 2 ? "var(--color-neutral)" : undefined }}>{fmtNum(r.volume_ratio)}</td>
                      <td className="tabular-nums" style={{ color: r.rsi > 70 ? "var(--color-bearish)" : r.rsi < 30 ? "var(--color-bullish)" : undefined }}>{fmtNum(r.rsi, 1)}</td>
                      <td className="tabular-nums">{fmtNum(r.adx, 1)}</td>
                      <td className="tabular-nums">{fmtPct(r.dist_52w_high)}</td>
                      <td className="text-xs whitespace-nowrap">{r.trend}</td>
                      <td><EntryBadge entry={r.entry} /></td>
                      <td className="tabular-nums">{r.probability_up != null ? `${(r.probability_up * 100).toFixed(0)}%` : "—"}</td>
                      <td><BucketChips buckets={r.buckets} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
