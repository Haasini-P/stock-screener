"use client";

import { useState } from "react";
import Link from "next/link";
import { Brain, ChevronRight, TrendingDown, TrendingUp } from "lucide-react";
import { marketAPI } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { fmtINR, fmtPct, humanize } from "@/lib/format";
import SearchBox from "../SearchBox";
import { Card, Change, EmptyState, ErrorState, LoadingRows, PageHeader, SectionHeader, StockLink } from "../ui";

const HORIZONS = ["1D", "3D", "5D", "10D", "20D"];
const RECENT_KEY = "stockmind_recent_predictions";

function ProbabilityBar({ up, flat, down }: { up: number; flat: number; down: number }) {
  return (
    <div className="h-2 rounded-full overflow-hidden flex w-full min-w-24" title={`Up ${(up * 100).toFixed(0)}% · Flat ${(flat * 100).toFixed(0)}% · Down ${(down * 100).toFixed(0)}%`}>
      <div style={{ width: `${up * 100}%`, background: "var(--color-bullish)" }} />
      <div style={{ width: `${flat * 100}%`, background: "var(--color-neutral)" }} />
      <div style={{ width: `${down * 100}%`, background: "var(--color-bearish)" }} />
    </div>
  );
}

function loadRecent(): string[] {
  try {
    return JSON.parse(localStorage.getItem(RECENT_KEY) || "[]");
  } catch {
    return [];
  }
}

/** Predictions for every horizon; succeeds if at least one horizon does. */
async function fetchAllHorizons(symbol: string): Promise<{ data: Record<string, any> }> {
  const settled = await Promise.allSettled(HORIZONS.map((h) => marketAPI.prediction(symbol, h)));
  const out: Record<string, any> = {};
  settled.forEach((s, i) => {
    if (s.status === "fulfilled") out[HORIZONS[i]] = s.value.data;
  });
  if (Object.keys(out).length === 0) {
    const failure = settled.find((s) => s.status === "rejected") as PromiseRejectedResult | undefined;
    throw failure?.reason ?? new Error(`Could not generate predictions for ${symbol}.`);
  }
  return { data: out };
}

export default function PredictionsView() {
  const [symbol, setSymbol] = useState("");
  // This view only renders client-side (tabs are chosen after hydration)
  const [recent, setRecent] = useState<string[]>(() => (typeof window !== "undefined" ? loadRecent() : []));

  const top = useApi(() => marketAPI.scanner({ sort_by: "probability_up", order: "desc" }), []);
  const predictions = useApi(() => fetchAllHorizons(symbol), [symbol], { enabled: !!symbol });
  const results = predictions.data || {};
  const loading = predictions.loading;
  const error = predictions.error;

  const select = (s: string) => {
    setSymbol(s);
    setRecent((prev) => {
      const next = [s, ...prev.filter((x) => x !== s)].slice(0, 8);
      try {
        localStorage.setItem(RECENT_KEY, JSON.stringify(next));
      } catch {}
      return next;
    });
  };

  const first = results["1D"] || Object.values(results)[0];

  return (
    <div className="space-y-5">
      <PageHeader title="Predictions" subtitle="Ensemble model direction probabilities across horizons. Probabilistic estimates — never a price promise." />

      <Card>
        <div className="flex flex-col md:flex-row gap-3 md:items-center">
          <SearchBox className="w-full md:max-w-md" placeholder="Enter a stock to predict (e.g. TCS)…" onSelect={select} />
          {recent.length > 0 && (
            <div className="flex flex-wrap gap-2 items-center">
              <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>Recent:</span>
              {recent.map((s) => (
                <button key={s} className={`chip ${s === symbol ? "chip-active" : ""}`} onClick={() => select(s)}>{s}</button>
              ))}
            </div>
          )}
        </div>
      </Card>

      {symbol && (
        <Card>
          <SectionHeader
            icon={<Brain size={16} />}
            title={`${symbol} — multi-horizon outlook`}
            subtitle={first ? `Confidence ${first.confidence} · risk ${first.risk}` : undefined}
            actions={
              <Link href={`/stock/${symbol}`} className="btn-secondary text-xs" style={{ padding: "6px 12px" }}>
                Full analysis <ChevronRight size={13} />
              </Link>
            }
          />
          {loading ? (
            <LoadingRows rows={5} />
          ) : error ? (
            <ErrorState message={error} onRetry={predictions.reload} />
          ) : (
            <>
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr><th>Horizon</th><th>Up</th><th>Flat</th><th>Down</th><th>Distribution</th><th>Expected return</th><th>Range (90%)</th><th>Signal</th></tr>
                  </thead>
                  <tbody>
                    {HORIZONS.filter((h) => results[h]).map((h) => {
                      const p = results[h];
                      const dp = p.direction_probabilities;
                      return (
                        <tr key={h}>
                          <td className="font-semibold">{h}</td>
                          <td className="tabular-nums text-bullish">{(dp.up * 100).toFixed(1)}%</td>
                          <td className="tabular-nums text-neutral-warn">{(dp.flat * 100).toFixed(1)}%</td>
                          <td className="tabular-nums text-bearish">{(dp.down * 100).toFixed(1)}%</td>
                          <td className="w-40"><ProbabilityBar {...dp} /></td>
                          <td className="tabular-nums">{p.expected_return != null ? fmtPct(p.expected_return * 100) : "—"}</td>
                          <td className="tabular-nums text-xs">
                            {p.prediction_interval ? `${fmtPct(p.prediction_interval.lower * 100)} to ${fmtPct(p.prediction_interval.upper * 100)}` : "—"}
                          </td>
                          <td>
                            <span className={`badge ${p.signal?.includes("upside") ? "badge-bullish" : p.signal?.includes("downside") ? "badge-bearish" : "badge-neutral"}`}>
                              {humanize(p.signal)}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {first?.explanation && <p className="text-xs mt-4 leading-relaxed" style={{ color: "var(--text-secondary)" }}>{first.explanation}</p>}
              {first && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
                  <div>
                    <p className="text-[11px] font-bold uppercase mb-2 text-bullish flex items-center gap-1"><TrendingUp size={12} /> Positive factors</p>
                    <ul className="space-y-1">
                      {(first.key_positive_factors || []).map((f: any, i: number) => (
                        <li key={i} className="text-xs" style={{ color: "var(--text-secondary)" }}>• {f.factor}</li>
                      ))}
                      {!first.key_positive_factors?.length && <li className="text-xs text-muted">None identified</li>}
                    </ul>
                  </div>
                  <div>
                    <p className="text-[11px] font-bold uppercase mb-2 text-bearish flex items-center gap-1"><TrendingDown size={12} /> Negative factors</p>
                    <ul className="space-y-1">
                      {(first.key_negative_factors || []).map((f: any, i: number) => (
                        <li key={i} className="text-xs" style={{ color: "var(--text-secondary)" }}>• {f.factor}</li>
                      ))}
                      {!first.key_negative_factors?.length && <li className="text-xs text-muted">None identified</li>}
                    </ul>
                  </div>
                </div>
              )}
            </>
          )}
        </Card>
      )}

      <Card>
        <SectionHeader title="Highest upside probability — approved universe" subtitle="5-day model probability from the latest scan. Click a stock to see all horizons." />
        {top.loading ? (
          <LoadingRows rows={6} />
        ) : top.error ? (
          <ErrorState message={top.error} onRetry={top.reload} />
        ) : !top.data?.results.length ? (
          <EmptyState title="No scan data yet" />
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead><tr><th>Stock</th><th>LTP</th><th>Day %</th><th>P(up) 5D</th><th>Confidence</th><th>Trend</th><th></th></tr></thead>
              <tbody>
                {top.data.results.slice(0, 15).map((r: any) => (
                  <tr key={r.symbol}>
                    <td><StockLink symbol={r.symbol} /><div className="text-[10px]" style={{ color: "var(--text-muted)" }}>{r.sector}</div></td>
                    <td className="tabular-nums">{fmtINR(r.ltp)}</td>
                    <td><Change value={r.change_pct} /></td>
                    <td className="tabular-nums font-semibold">{(r.probability_up * 100).toFixed(1)}%</td>
                    <td className="text-xs">{r.confidence}</td>
                    <td className="text-xs">{r.trend}</td>
                    <td>
                      <button className="btn-ghost text-xs" onClick={() => { select(r.symbol); window.scrollTo({ top: 0, behavior: "smooth" }); }}>
                        Predict <ChevronRight size={12} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
