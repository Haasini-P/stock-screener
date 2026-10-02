/**
 * Buckets raw 1-minute candles into coarser intraday bars (5m/15m/30m/1h) by
 * real OHLC aggregation — not sampling a live price every poll tick, which
 * would miss whatever happened between polls. Indian markets run on IST
 * (UTC+5:30); flooring raw UTC epoch ms to a clock boundary would misalign
 * every bucket by 30 minutes from what a trader expects (a "1-hour" candle
 * starting at 9:30 UTC instead of 10:00 IST), so the IST offset is applied
 * before flooring and removed after.
 */

import { CandleRow } from "./candleAnalysis";

const IST_OFFSET_MS = 5.5 * 60 * 60 * 1000;

export function aggregateCandles(rows: CandleRow[], bucketMinutes: number): CandleRow[] {
  if (bucketMinutes <= 1 || rows.length === 0) return rows;
  const bucketMs = bucketMinutes * 60_000;
  const out: CandleRow[] = [];
  let current: CandleRow | null = null;
  let currentBucketStart = NaN;

  for (const r of rows) {
    const t = typeof r.time === "number" ? r.time : new Date(r.time).getTime();
    const bucketStart = Math.floor((t + IST_OFFSET_MS) / bucketMs) * bucketMs - IST_OFFSET_MS;

    if (!current || bucketStart !== currentBucketStart) {
      if (current) out.push(current);
      current = { time: bucketStart, open: r.open, high: r.high, low: r.low, close: r.close, volume: r.volume };
      currentBucketStart = bucketStart;
    } else {
      current.high = Math.max(current.high, r.high);
      current.low = Math.min(current.low, r.low);
      current.close = r.close;
      current.volume += r.volume;
    }
  }
  if (current) out.push(current);
  return out;
}
