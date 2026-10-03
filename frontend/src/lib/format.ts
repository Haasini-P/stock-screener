/**
 * StockMind AI — Display formatters (Indian locale).
 */

export const fmtNum = (v: number | null | undefined, digits = 2): string =>
  v == null || Number.isNaN(v)
    ? "—"
    : v.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits });

export const fmtINR = (v: number | null | undefined, digits = 2): string =>
  v == null || Number.isNaN(v) ? "—" : `₹${fmtNum(v, digits)}`;

export const fmtUSD = (v: number | null | undefined, digits = 2): string =>
  v == null || Number.isNaN(v) ? "—" : `$${v.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;

/** Compact ₹ amounts: 1.2 L, 3.4 Cr. */
export const fmtINRCompact = (v: number | null | undefined): string => {
  if (v == null || Number.isNaN(v)) return "—";
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (abs >= 1e7) return `${sign}₹${(abs / 1e7).toFixed(2)} Cr`;
  if (abs >= 1e5) return `${sign}₹${(abs / 1e5).toFixed(2)} L`;
  return `${sign}₹${fmtNum(abs, 0)}`;
};

export const fmtPct = (v: number | null | undefined, digits = 2): string =>
  v == null || Number.isNaN(v) ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(digits)}%`;

export const fmtVolume = (v: number | null | undefined): string => {
  if (v == null) return "—";
  if (v >= 1e7) return `${(v / 1e7).toFixed(2)} Cr`;
  if (v >= 1e5) return `${(v / 1e5).toFixed(2)} L`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(1)} K`;
  return String(v);
};

export const tone = (v: number | null | undefined): "bullish" | "bearish" | "neutral" =>
  v == null || v === 0 ? "neutral" : v > 0 ? "bullish" : "bearish";

export const toneColor = (v: number | null | undefined): string =>
  ({ bullish: "var(--color-bullish)", bearish: "var(--color-bearish)", neutral: "var(--text-secondary)" })[tone(v)];

export const timeAgo = (iso: string | null | undefined): string => {
  if (!iso) return "";
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
};

export const fmtTime = (iso: string | null | undefined): string =>
  iso
    ? new Date(iso).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata" })
    : "—";

export const fmtDate = (iso: string | null | undefined): string =>
  iso ? new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "—";

export const humanize = (s: string | null | undefined): string =>
  s ? s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) : "—";
