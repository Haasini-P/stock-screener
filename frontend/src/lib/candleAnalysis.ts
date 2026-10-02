/**
 * Rule-based candlestick analysis — a per-candle "what would an institutional
 * desk read into this, and what would they need to see before acting on it"
 * note. Deliberately deterministic (no LLM call per candle: that would be
 * slow, costly, and not actually how candle patterns are read — they're
 * precise geometric rules, not something to ask a language model to eyeball).
 */

export interface CandleRow {
  time: number | string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface CandleNote {
  pattern: string | null;
  tone: "bullish" | "bearish" | "neutral";
  text: string;
}

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

function fmt(n: number): string {
  return n.toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

function trendContext(close: number, ma50: number | null, ma200: number | null): string {
  if (ma50 == null || ma200 == null) return "not enough history yet to read the broader trend (need 200+ candles).";
  if (close > ma50 && close > ma200) return `above both the 50-day (₹${fmt(ma50)}) and 200-day (₹${fmt(ma200)}) MAs — broader uptrend intact.`;
  if (close < ma50 && close < ma200) return `below both the 50-day (₹${fmt(ma50)}) and 200-day (₹${fmt(ma200)}) MAs — broader downtrend intact.`;
  return `between the 50-day (₹${fmt(ma50)}) and 200-day (₹${fmt(ma200)}) MAs — trend is mixed/transitioning, not yet confirmed either way.`;
}

/**
 * One note per candle: a base trend-confirmation read for every candle, and
 * for the ones that form a recognized pattern, the pattern name plus the
 * specific follow-through an institutional desk would require before acting
 * on it (never "this candle alone confirms X" — confirmation needs the next
 * candle and volume, by design).
 */
export function analyzeCandles(rows: CandleRow[]): CandleNote[] {
  const closes = rows.map((r) => r.close);
  const volumes = rows.map((r) => r.volume);
  const ma50 = sma(closes, 50);
  const ma200 = sma(closes, 200);
  const volAvg20 = sma(volumes, 20);

  return rows.map((r, i) => {
    const body = Math.abs(r.close - r.open);
    const range = r.high - r.low || 1e-9;
    const upperWick = r.high - Math.max(r.open, r.close);
    const lowerWick = Math.min(r.open, r.close) - r.low;
    const isBullish = r.close > r.open;
    const isBearish = r.close < r.open;
    const trend = trendContext(r.close, ma50[i], ma200[i]);
    const volRatio = volAvg20[i] ? r.volume / (volAvg20[i] as number) : null;
    const volText = volRatio != null ? `Volume today is ${volRatio.toFixed(1)}× the 20-day average.` : "Not enough history yet for a volume baseline.";

    const prev = rows[i - 1];
    const prev2 = rows[i - 2];

    // --- 3-candle patterns (checked first — most specific) ---
    if (prev && prev2) {
      // Morning Star: big red, small indecisive body gapping down, big green closing above first candle's midpoint
      if (
        prev2.close < prev2.open && Math.abs(prev2.close - prev2.open) > range * 0.5 &&
        Math.abs(prev.close - prev.open) < Math.abs(prev2.close - prev2.open) * 0.4 &&
        isBullish && r.close > (prev2.open + prev2.close) / 2
      ) {
        return {
          pattern: "Morning Star",
          tone: "bullish",
          text: `Morning Star over the last 3 candles — a sharp selloff, a stall, then a strong reversal candle closing back above the first candle's midpoint. This is one of the stronger reversal signals, but a desk would still want tomorrow's candle to hold above today's close before adding size. Price is ${trend} ${volText}`,
        };
      }
      // Evening Star: mirror
      if (
        prev2.close > prev2.open && Math.abs(prev2.close - prev2.open) > range * 0.5 &&
        Math.abs(prev.close - prev.open) < Math.abs(prev2.close - prev2.open) * 0.4 &&
        isBearish && r.close < (prev2.open + prev2.close) / 2
      ) {
        return {
          pattern: "Evening Star",
          tone: "bearish",
          text: `Evening Star over the last 3 candles — a strong rally, a stall, then a sharp reversal candle closing back below the first candle's midpoint. Treat as a distribution warning; confirmation needs tomorrow's candle to hold below today's close on above-average volume. Price is ${trend} ${volText}`,
        };
      }
    }

    // --- 2-candle patterns ---
    if (prev) {
      const prevBearish = prev.close < prev.open;
      const prevBullish = prev.close > prev.open;
      if (prevBearish && isBullish && r.open <= prev.close && r.close >= prev.open) {
        return {
          pattern: "Bullish Engulfing",
          tone: "bullish",
          text: `Bullish Engulfing — today's green body fully covers yesterday's red body. An institutional desk would not act on this alone: it needs (1) a follow-through close above today's high (₹${fmt(r.high)}) on the next session, and (2) volume confirmation — ${volText} Price is ${trend}`,
        };
      }
      if (prevBullish && isBearish && r.open >= prev.close && r.close <= prev.open) {
        return {
          pattern: "Bearish Engulfing",
          tone: "bearish",
          text: `Bearish Engulfing — today's red body fully covers yesterday's green body. Confirmation would require a follow-through close below today's low (₹${fmt(r.low)}) on the next session, plus volume support — ${volText} Price is ${trend}`,
        };
      }
    }

    // --- single-candle patterns ---
    if (body <= range * 0.1) {
      return {
        pattern: "Doji",
        tone: "neutral",
        text: `Doji — open and close are nearly identical, meaning neither buyers nor sellers won the session. On its own this is indecision, not a signal; it only matters in context — read it as a possible pause/reversal warning if it appears after an extended move, and ignore it inside a trend's normal consolidation. Price is ${trend} ${volText}`,
      };
    }
    if (lowerWick >= body * 2 && upperWick <= body * 0.5) {
      return {
        pattern: "Hammer",
        tone: "bullish",
        text: `Hammer — a long lower wick shows sellers pushed price down intraday but buyers reclaimed most of it by the close. Only meaningful as a reversal signal after a decline; confirmation needs the next candle to close above this candle's body on rising volume (today: ${volText.toLowerCase()}). Price is ${trend}`,
      };
    }
    if (upperWick >= body * 2 && lowerWick <= body * 0.5) {
      return {
        pattern: "Shooting Star",
        tone: "bearish",
        text: `Shooting Star — a long upper wick shows buyers pushed price up intraday but sellers took it back by the close. Only meaningful after an advance; confirmation needs the next candle to close below this candle's body, ideally on rising volume. ${volText} Price is ${trend}`,
      };
    }

    // No classic pattern — still give the trend-confirmation read every candle deserves.
    return {
      pattern: null,
      tone: isBullish ? "bullish" : isBearish ? "bearish" : "neutral",
      text: `No classic reversal/continuation pattern on this candle — a plain ${isBullish ? "up" : isBearish ? "down" : "flat"} day. Price is ${trend} ${volText}`,
    };
  });
}
