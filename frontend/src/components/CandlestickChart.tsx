"use client";

/**
 * Real OHLC candlesticks (bullish/bearish bodies + wicks) plus volume and
 * 20/50/200-day moving averages, built straight from the same Upstox candle
 * data the rest of the app uses (marketAPI.candles) — this is the visual
 * counterpart to the AI commentary's chart analysis section. Resizable
 * (drag the handle below the chart), live-updating (polls on the same
 * interval as the rest of the app and appends/extends bars in place rather
 * than rebuilding, so zoom/scroll survive), and every candle gets a hover
 * tooltip with a rule-based institutional-style read: pattern name (if any)
 * plus exactly what would need to happen next to actually confirm it — never
 * a single candle "confirms" a trend on its own.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import {
  CandlestickSeries, createChart, createSeriesMarkers, CrosshairMode, HistogramSeries, IChartApi, ISeriesApi, LineSeries, SeriesMarker, Time,
} from "lightweight-charts";
import { Activity, Maximize2, Minimize2 } from "lucide-react";
import { marketAPI, usMarketAPI } from "@/lib/api";
import { useAppStore } from "@/lib/store";
import { useApi } from "@/lib/useApi";
import { analyzeCandles, CandleRow } from "@/lib/candleAnalysis";
import { aggregateCandles } from "@/lib/aggregateCandles";
import { EmptyState, ErrorState, SectionHeader, Skeleton } from "./ui";

const RANGES = ["1D", "1M", "3M", "6M", "1Y", "5Y"] as const;
// Only meaningful for the 1D (intraday) range — real OHLC aggregation of the
// raw 1-minute candles, not a resample of sparse live-price samples.
const BUCKETS = [
  { minutes: 1, label: "1m" },
  { minutes: 5, label: "5m" },
  { minutes: 15, label: "15m" },
  { minutes: 30, label: "30m" },
  { minutes: 60, label: "1h" },
];
const MAS: { period: number; color: string }[] = [
  { period: 20, color: "#f59e0b" },
  { period: 50, color: "#6366f1" },
  { period: 200, color: "#a855f7" },
];
const MIN_HEIGHT = 220;
const MAX_HEIGHT = 720;
const TONE_COLOR: Record<string, string> = { bullish: "#22c55e", bearish: "#ef4444", neutral: "#f59e0b" };

function sma(values: number[], period: number): (number | null)[] {
  const out: (number | null)[] = [];
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    sum += values[i];
    if (i >= period) sum -= values[i - period];
    out.push(i >= period - 1 ? sum / period : null);
  }
  return out;
}

function toTime(t: string | number): Time {
  const ms = typeof t === "number" ? t : new Date(t).getTime();
  return Math.floor(ms / 1000) as Time;
}

function barColor(open: number, close: number): string {
  return close >= open ? "rgba(34,197,94,0.35)" : "rgba(239,68,68,0.35)";
}

export default function CandlestickChart({ symbol, market = "IN" }: { symbol: string; market?: "IN" | "US" }) {
  const { settings } = useAppStore();
  // US candles are daily-only for now (see backend/app/services/us_market/provider.py) —
  // no intraday source wired in yet, so 1D/bucket selection doesn't apply there.
  const ranges = market === "US" ? RANGES.filter((r) => r !== "1D") : RANGES;
  const [range, setRange] = useState<(typeof RANGES)[number]>("6M");
  const [bucketMinutes, setBucketMinutes] = useState(1);
  const [height, setHeight] = useState(320);
  const [fullscreen, setFullscreen] = useState(false);
  const interval = range === "5Y" ? "week" : range === "1D" ? "1minute" : "day";
  // Polls on the same cadence as the rest of the app (settings.refreshSec; 0 = off).
  // The effect below only ever does a full chart rebuild when symbol/range/bucket
  // actually change — a poll arriving for the same selection takes the cheap
  // incremental path (series.update() on just the new/changed tail bars).
  const fetchCandles = market === "US" ? usMarketAPI.candles : marketAPI.candles;
  const candles = useApi(() => fetchCandles(symbol, range, interval), [symbol, market, range], { refreshMs: settings.refreshSec * 1000 });
  const rawRows: CandleRow[] = candles.data?.candles || [];
  const rows = useMemo(
    () => (range === "1D" ? aggregateCandles(rawRows, bucketMinutes) : rawRows),
    // candles.data (not rawRows, a fresh array literal every render) is the stable trigger.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [candles.data, range, bucketMinutes]
  );

  const wrapperRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const maSeriesRef = useRef<{ period: number; series: ISeriesApi<"Line"> }[]>([]);
  const lastBarTimeRef = useRef<number | null>(null);
  const buildKeyRef = useRef<string>("");
  const tooltipRef = useRef<HTMLDivElement>(null);
  const tooltipTitleRef = useRef<HTMLDivElement>(null);
  const tooltipMetaRef = useRef<HTMLDivElement>(null);
  const tooltipBodyRef = useRef<HTMLDivElement>(null);
  const resizingRef = useRef(false);

  // A CSS "fixed" overlay would get trapped inside the Card's bounds — Card uses
  // backdrop-filter for its glass effect, and filter/backdrop-filter/transform on
  // an ancestor creates a new containing block for position:fixed descendants.
  // The real Fullscreen API sidesteps that entirely: the browser promotes the
  // element to the top layer, above every stacking/containing context.
  useEffect(() => {
    const onChange = () => setFullscreen(document.fullscreenElement === wrapperRef.current);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  const toggleFullscreen = () => {
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else {
      wrapperRef.current?.requestFullscreen().catch(() => {
        // Fullscreen can be denied outside a trusted user gesture or by browser policy —
        // fall back to the resizable inline view rather than silently doing nothing.
      });
    }
  };

  const onResizeStart = (e: React.MouseEvent) => {
    e.preventDefault();
    resizingRef.current = true;
    const startY = e.clientY;
    const startHeight = height;
    const onMove = (ev: MouseEvent) => {
      if (!resizingRef.current) return;
      setHeight(Math.min(MAX_HEIGHT, Math.max(MIN_HEIGHT, startHeight + (ev.clientY - startY))));
    };
    const onUp = () => {
      resizingRef.current = false;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  useEffect(() => {
    if (!containerRef.current || rows.length === 0) return;
    const key = `${symbol}:${range}:${bucketMinutes}`;

    // Same selection, fresh poll data — nudge just the new/changed tail bars
    // (covers both "same bar extended" and "one or more new bars opened" since
    // the last update) instead of rebuilding the whole chart and losing zoom.
    if (buildKeyRef.current === key) {
      const candleSeries = candleSeriesRef.current;
      const volumeSeries = volumeSeriesRef.current;
      if (!candleSeries) return;
      const lastTime = lastBarTimeRef.current;
      const tail = lastTime == null ? rows : rows.filter((r) => (toTime(r.time) as number) >= lastTime);
      const closes = rows.map((r) => r.close);
      for (const r of tail) {
        const t = toTime(r.time);
        candleSeries.update({ time: t, open: r.open, high: r.high, low: r.low, close: r.close });
        volumeSeries?.update({ time: t, value: r.volume, color: barColor(r.open, r.close) });
        lastBarTimeRef.current = t as number;
      }
      for (const { period, series } of maSeriesRef.current) {
        const values = sma(closes, period);
        for (const r of tail) {
          const idx = rows.indexOf(r);
          if (values[idx] != null) series.update({ time: toTime(r.time), value: values[idx] as number });
        }
      }
      return;
    }

    // Selection changed (or first load for it) — full rebuild.
    buildKeyRef.current = key;

    const chart = createChart(containerRef.current, {
      layout: { background: { color: "transparent" }, textColor: "#8a91a8", fontSize: 11 },
      grid: { vertLines: { visible: false }, horzLines: { color: "rgba(255,255,255,0.05)" } },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false, timeVisible: range === "1D" },
      crosshair: { mode: CrosshairMode.Normal },
      autoSize: true,
    });
    chartRef.current = chart;

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e", downColor: "#ef4444", borderVisible: false,
      wickUpColor: "#22c55e", wickDownColor: "#ef4444",
    });
    const candleData = rows.map((r) => ({ time: toTime(r.time), open: r.open, high: r.high, low: r.low, close: r.close }));
    candleSeries.setData(candleData);
    candleSeriesRef.current = candleSeries;
    lastBarTimeRef.current = (candleData[candleData.length - 1]?.time as number) ?? null;

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
      lastValueVisible: false,
      priceLineVisible: false,
    });
    chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    volumeSeries.setData(rows.map((r) => ({ time: toTime(r.time), value: r.volume, color: barColor(r.open, r.close) })));
    volumeSeriesRef.current = volumeSeries;

    const closes = rows.map((r) => r.close);
    maSeriesRef.current = [];
    for (const { period, color } of MAS) {
      if (rows.length <= period) continue;
      const values = sma(closes, period);
      const maSeries = chart.addSeries(LineSeries, {
        color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
      });
      maSeries.setData(
        candleData
          .map((d, i) => ({ time: d.time, value: values[i] as number }))
          .filter((d) => d.value != null)
      );
      maSeriesRef.current.push({ period, series: maSeries });
    }

    // Rule-based per-candle read (pattern + trend-confirmation checklist) — see
    // lib/candleAnalysis.ts. Patterned candles get a marker; every candle gets
    // a hover tooltip via the crosshair handler below. Only computed on a full
    // rebuild — the live-ticking bar picks up its note next time this reruns.
    const notes = analyzeCandles(rows);
    const timeToIndex = new Map<number, number>();
    candleData.forEach((d, i) => timeToIndex.set(d.time as number, i));

    const markers: SeriesMarker<Time>[] = candleData
      .map((d, i) => ({ d, note: notes[i] }))
      .filter(({ note }) => note.pattern)
      .map(({ d, note }) => ({
        time: d.time,
        position: note.tone === "bullish" ? "belowBar" : note.tone === "bearish" ? "aboveBar" : "inBar",
        shape: note.tone === "bullish" ? "arrowUp" : note.tone === "bearish" ? "arrowDown" : "circle",
        color: TONE_COLOR[note.tone],
        text: note.pattern as string,
      }));
    if (markers.length) createSeriesMarkers(candleSeries, markers);

    chart.subscribeCrosshairMove((param) => {
      const tooltip = tooltipRef.current;
      if (!tooltip) return;
      if (!param.point || param.time == null || param.point.x < 0 || param.point.y < 0) {
        tooltip.style.display = "none";
        return;
      }
      const idx = timeToIndex.get(param.time as number);
      if (idx == null) {
        tooltip.style.display = "none";
        return;
      }
      const r = rows[idx];
      const note = notes[idx];
      const dateLabel = new Date((param.time as number) * 1000).toLocaleDateString("en-IN", {
        day: "numeric", month: "short", year: "numeric", ...(range === "1D" ? { hour: "2-digit", minute: "2-digit" } : {}),
      });

      if (tooltipTitleRef.current) {
        tooltipTitleRef.current.textContent = note.pattern || "Candle read";
        tooltipTitleRef.current.style.color = TONE_COLOR[note.tone];
      }
      if (tooltipMetaRef.current) {
        tooltipMetaRef.current.textContent =
          `${dateLabel} · O ${r.open.toFixed(2)} H ${r.high.toFixed(2)} L ${r.low.toFixed(2)} C ${r.close.toFixed(2)}`;
      }
      if (tooltipBodyRef.current) tooltipBodyRef.current.textContent = note.text;

      const containerWidth = containerRef.current?.clientWidth || 0;
      const tooltipWidth = 300;
      let left = param.point.x + 16;
      if (left + tooltipWidth > containerWidth) left = Math.max(0, param.point.x - tooltipWidth - 16);
      tooltip.style.left = `${left}px`;
      tooltip.style.top = `${Math.max(0, param.point.y - 12)}px`;
      tooltip.style.display = "block";
    });

    chart.timeScale().fitContent();

    return () => {
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
      maSeriesRef.current = [];
      lastBarTimeRef.current = null;
      buildKeyRef.current = "";
    };
  }, [candles.data, range, bucketMinutes, symbol, rows]);

  return (
    <div
      ref={wrapperRef}
      className={fullscreen ? "w-full h-full p-4 flex flex-col" : ""}
      style={fullscreen ? { background: "var(--bg-primary)" } : undefined}
    >
      <SectionHeader
        icon={<Activity size={16} />}
        title="Chart Analysis"
        subtitle={`Candles, volume, 20/50/200-day MAs & per-candle pattern read — source: ${market === "US" ? "Alpaca (~15-min delayed)" : "Upstox"}`}
        actions={
          <>
            {range === "1D" && BUCKETS.map((b) => (
              <button key={b.minutes} className={`chip ${bucketMinutes === b.minutes ? "chip-active" : ""}`} onClick={() => setBucketMinutes(b.minutes)}>
                {b.label}
              </button>
            ))}
            {ranges.map((r) => (
              <button key={r} className={`chip ${range === r ? "chip-active" : ""}`} onClick={() => setRange(r)}>{r}</button>
            ))}
            <button className="btn-ghost text-xs" style={{ padding: "4px 8px" }} onClick={toggleFullscreen} title={fullscreen ? "Exit full screen (Esc)" : "Full screen"}>
              {fullscreen ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
            </button>
          </>
        }
      />
      {candles.loading ? (
        <Skeleton className="h-80 w-full" />
      ) : candles.error ? (
        <ErrorState message={candles.error} onRetry={candles.reload} />
      ) : rows.length === 0 ? (
        <EmptyState title="No candles for this range" />
      ) : (
        <div className={fullscreen ? "relative flex-1 min-h-0" : "relative"}>
          <div ref={containerRef} className="w-full" style={fullscreen ? { height: "100%" } : { height }} />
          <div
            ref={tooltipRef}
            className="absolute pointer-events-none rounded-lg p-2.5 z-10"
            style={{
              display: "none", width: 300, background: "var(--bg-secondary)",
              border: "1px solid var(--border-subtle)", boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
            }}
          >
            <div ref={tooltipTitleRef} className="text-xs font-bold mb-1" />
            <div ref={tooltipMetaRef} className="text-[10px] mb-1.5 tabular-nums" style={{ color: "var(--text-muted)" }} />
            <div ref={tooltipBodyRef} className="text-[11px] leading-relaxed" style={{ color: "var(--text-secondary)" }} />
          </div>
          {!fullscreen && (
            <div
              onMouseDown={onResizeStart}
              className="w-full flex items-center justify-center"
              style={{ height: 14, cursor: "ns-resize" }}
              title="Drag to resize"
            >
              <div style={{ width: 36, height: 4, borderRadius: 2, background: "var(--border-subtle)" }} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
