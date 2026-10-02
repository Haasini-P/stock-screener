/**
 * StockMind AI — Buy/avoid verdict wording, shared by the Market Scanner and
 * the Stock Report so both state the same recommendation the same way.
 */

import { humanize } from "./format";

export type EvidenceFactor = { factor: string };

export interface VerdictInput {
  entry: string | null | undefined;
  evidence?: { positive?: EvidenceFactor[]; negative?: EvidenceFactor[] } | null;
  explanation?: string | null;
  probability_up?: number | null;
  risk_reward?: number | null;
}

const TONE: Record<string, "bullish" | "bearish" | "neutral" | "info"> = {
  BUY_NOW: "bullish",
  BUY_ON_RETEST: "bullish",
  BUY_ON_DIP: "info",
  BREAKOUT_WATCH: "info",
  WAIT: "neutral",
  EXTENDED: "neutral",
  AVOID: "bearish",
};

const TONE_COLOR: Record<string, string> = {
  bullish: "var(--color-bullish)",
  bearish: "var(--color-bearish)",
  neutral: "var(--color-neutral)",
  info: "var(--color-info)",
};

/** Color for a verdict's entry classification — matches EntryBadge's palette. */
export function verdictColor(entry: string | null | undefined): string {
  return TONE_COLOR[TONE[entry || ""] || "neutral"];
}

export function verdictLabel(entry: string | null | undefined): string {
  return entry ? humanize(entry.toLowerCase()) : "No signal";
}

/** Is this classification actionable as a buy right now? */
export function isBuyVerdict(entry: string | null | undefined): boolean {
  return entry === "BUY_NOW" || entry === "BUY_ON_RETEST" || entry === "BUY_ON_DIP";
}

/**
 * Compose a short plain-English recommendation sentence from a signal's
 * entry classification and evidence. Falls back to the raw `explanation`
 * when there isn't enough evidence to build a fuller sentence.
 */
export function buildRecommendation(input: VerdictInput): string {
  const { entry, evidence, explanation, probability_up, risk_reward } = input;
  const positives = (evidence?.positive || []).map((e) => e.factor).filter(Boolean);
  const negatives = (evidence?.negative || []).map((e) => e.factor).filter(Boolean);

  if (!positives.length && !negatives.length) {
    return explanation || "Insufficient evidence for a clear signal.";
  }

  const label = verdictLabel(entry).toUpperCase();
  const parts: string[] = [];

  if (positives.length) {
    parts.push(`${label} — ${positives.slice(0, 2).join(" and ")} support this`);
  } else {
    parts.push(label);
  }

  const stats: string[] = [];
  if (probability_up != null) stats.push(`P(up) ${(probability_up * 100).toFixed(0)}%`);
  if (risk_reward != null) stats.push(`R:R 1:${risk_reward}`);
  if (stats.length) parts[0] += ` (${stats.join(", ")})`;

  if (negatives.length) {
    parts.push(`Risk: ${negatives[0]}`);
  }

  return parts.join(". ") + ".";
}
