"use client";

/**
 * StockMind AI — Shared UI primitives.
 */

import { ReactNode, useEffect } from "react";
import Link from "next/link";
import { AlertTriangle, CheckCircle2, Info, Inbox, RefreshCw, X, XCircle } from "lucide-react";
import { fmtPct, humanize, toneColor } from "@/lib/format";
import { useAppStore } from "@/lib/store";

export function Card({
  children,
  className = "",
  padded = true,
  accent,
}: {
  children: ReactNode;
  className?: string;
  padded?: boolean;
  accent?: string;
}) {
  return (
    <div
      className={`glass-card-static ${padded ? "p-5" : ""} ${className}`}
      style={accent ? { borderLeft: `3px solid ${accent}` } : undefined}
    >
      {children}
    </div>
  );
}

export function SectionHeader({
  icon,
  title,
  subtitle,
  actions,
}: {
  icon?: ReactNode;
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
      <div className="flex items-start gap-2 min-w-0">
        {icon && <span className="mt-0.5" style={{ color: "var(--accent-indigo)" }}>{icon}</span>}
        <div className="min-w-0">
          <h3 className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>{title}</h3>
          {subtitle && <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>{subtitle}</p>}
        </div>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3 mb-5">
      <div>
        <h1 className="text-xl font-bold tracking-tight" style={{ color: "var(--text-primary)" }}>{title}</h1>
        {subtitle && <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function RefreshButton({
  onClick,
  busy,
  label = "Refresh",
  updatedAt,
}: {
  onClick: () => void;
  busy?: boolean;
  label?: string;
  updatedAt?: Date | null;
}) {
  return (
    <div className="flex items-center gap-2">
      {updatedAt && (
        <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>
          Updated {updatedAt.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
        </span>
      )}
      <button className="btn-secondary text-xs" style={{ padding: "6px 12px" }} onClick={onClick} disabled={busy}>
        <RefreshCw size={13} className={busy ? "animate-spin" : ""} /> {label}
      </button>
    </div>
  );
}

export function Skeleton({ className = "h-4 w-full" }: { className?: string }) {
  return <div className={`skeleton rounded ${className}`} />;
}

export function LoadingRows({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-8 w-full" />
      ))}
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div
      className="flex flex-col items-center justify-center text-center py-10 px-4 rounded-lg"
      style={{ background: "rgba(99, 102, 241, 0.03)", border: "1px dashed var(--border-default)" }}
    >
      <span className="mb-3" style={{ color: "var(--accent-indigo)" }}>{icon || <Inbox size={28} />}</span>
      <p className="text-sm font-semibold mb-1" style={{ color: "var(--text-primary)" }}>{title}</p>
      {description && <p className="text-xs max-w-md" style={{ color: "var(--text-muted)" }}>{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div
      className="flex items-start gap-3 p-4 rounded-lg"
      style={{ background: "var(--color-bearish-bg)", border: "1px solid var(--color-bearish-border)" }}
      role="alert"
    >
      <AlertTriangle size={16} style={{ color: "var(--color-bearish)", flexShrink: 0, marginTop: 1 }} />
      <div className="flex-1 text-xs" style={{ color: "var(--text-primary)" }}>{message}</div>
      {onRetry && (
        <button className="btn-ghost text-xs" onClick={onRetry}>
          <RefreshCw size={12} /> Retry
        </button>
      )}
    </div>
  );
}

export function Change({ value, className = "" }: { value: number | null | undefined; className?: string }) {
  return (
    <span className={`font-semibold tabular-nums ${className}`} style={{ color: toneColor(value) }}>
      {fmtPct(value)}
    </span>
  );
}

const ENTRY_STYLE: Record<string, string> = {
  BUY_NOW: "badge-bullish",
  BUY_ON_RETEST: "badge-bullish",
  BUY_ON_DIP: "badge-info",
  BREAKOUT_WATCH: "badge-info",
  WAIT: "badge-neutral",
  EXTENDED: "badge-neutral",
  AVOID: "badge-bearish",
};

// What each entry classification actually means — shown as a hover tooltip so the
// badge text ("Breakout Watch", "Buy On Retest"...) isn't the only explanation offered.
const ENTRY_TOOLTIP: Record<string, string> = {
  BUY_NOW: "Strong setup with confirming volume in a favorable market regime — supports buying now rather than waiting for a pullback.",
  BUY_ON_RETEST: "A strong setup, but the market regime (or a more moderate score) calls for waiting for a pullback/retest instead of chasing the current price.",
  BUY_ON_DIP: "Set up for a dip-buy inside an already-established uptrend.",
  BREAKOUT_WATCH: "An early, not-yet-confirmed positive setup — worth watching for confirmation (rising volume, a clean break of resistance) before entering.",
  WAIT: "No clear edge either way right now — the technicals don't support an entry yet, but nothing rules one out either.",
  EXTENDED: "Price has already moved too far, too fast (a big 5-day gain, or RSI above 80) — chasing here risks buying right before a pullback.",
  AVOID: "Technicals are currently working against this stock — an entry isn't supported right now.",
};

export function EntryBadge({ entry }: { entry: string | null | undefined }) {
  if (!entry) return <span className="text-muted">—</span>;
  return (
    <span className={`badge ${ENTRY_STYLE[entry] || "badge-neutral"}`} title={ENTRY_TOOLTIP[entry] || undefined}>
      {humanize(entry.toLowerCase())}
    </span>
  );
}

// What each scanner "setup" bucket actually screens for and the holding period it's
// designed around — mirrors BUCKET_TERM_MAP in app/services/analytics/watchlist_service.py.
const BUCKET_TOOLTIP: Record<string, string> = {
  momentum_breakout: "Volume-driven breakout already underway (strong trend, RSI 55-70). Tends to play out over days, not held long — a short-term setup.",
  breakout_retest: "Near its 52-week high with volume cooling off — waiting for a retest entry inside a recent breakout. Short-term: triggers within days to a couple of weeks.",
  early_stage_breakout: "A volatility-compression base just starting to break out on rising volume. Typically weeks to a couple of months to play out — a medium-term setup.",
  quality_pullback: "A dip inside a stock whose 200-day trend is still intact (buy-the-dip in an uptrend). Meant to be held while that longer trend plays out — a long-term setup.",
};

export function BucketChips({ buckets }: { buckets: string[] | undefined }) {
  if (!buckets?.length) return <span className="text-muted">—</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {buckets.map((b) => (
        <span key={b} className="badge badge-accent" style={{ fontSize: 9 }} title={BUCKET_TOOLTIP[b] || undefined}>{humanize(b)}</span>
      ))}
    </div>
  );
}

const BADGE_PALETTE = ["#6366f1", "#22c55e", "#f59e0b", "#ec4899", "#14b8a6", "#a855f7", "#ef4444", "#22d3ee"];

/** Colored rounded badge with a stock's first 1-2 letters — a stand-in for a
 * company logo (no external images/logo API), mirroring the tinted-square
 * style already used for sector icons (background: `${color}15`, color).
 * The color is deterministic per symbol (simple hash into a fixed palette),
 * not random, so a given stock always gets the same color across renders. */
export function InitialsBadge({ symbol, size = 32 }: { symbol: string; size?: number }) {
  const letters = symbol.slice(0, 2).toUpperCase();
  const hash = symbol.split("").reduce((acc, ch) => acc + ch.charCodeAt(0), 0);
  const color = BADGE_PALETTE[hash % BADGE_PALETTE.length];
  return (
    <div
      className="rounded-lg flex items-center justify-center shrink-0 font-bold"
      style={{ width: size, height: size, background: `${color}20`, color, fontSize: size * 0.34 }}
    >
      {letters}
    </div>
  );
}

export function StockLink({ symbol, className = "" }: { symbol: string; className?: string }) {
  return (
    <Link
      href={`/stock/${encodeURIComponent(symbol)}`}
      className={`font-semibold hover:underline ${className}`}
      style={{ color: "var(--text-primary)" }}
    >
      {symbol}
    </Link>
  );
}

export function Modal({
  open,
  onClose,
  title,
  children,
  maxWidth = "max-w-md",
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  maxWidth?: string;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.6)" }}
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <div className={`glass-card-static w-full ${maxWidth} p-5 animate-fade-in`} style={{ background: "var(--bg-secondary)" }}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>{title}</h2>
          <button className="btn-ghost" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Toaster() {
  const { toasts, dismissToast } = useAppStore();
  const icons = {
    success: <CheckCircle2 size={16} style={{ color: "var(--color-bullish)" }} />,
    error: <XCircle size={16} style={{ color: "var(--color-bearish)" }} />,
    info: <Info size={16} style={{ color: "var(--color-info)" }} />,
  };
  return (
    <div className="fixed bottom-4 right-4 z-[80] flex flex-col gap-2" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className="toast">
          {icons[t.kind]}
          <span className="flex-1">{t.message}</span>
          <button onClick={() => dismissToast(t.id)} aria-label="Dismiss" style={{ color: "var(--text-muted)" }}>
            <X size={14} />
          </button>
        </div>
      ))}
    </div>
  );
}

export function KeyValue({ label, value, valueColor }: { label: string; value: ReactNode; valueColor?: string }) {
  return (
    <div>
      <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>{label}</p>
      <p className="text-sm font-semibold tabular-nums" style={{ color: valueColor || "var(--text-primary)" }}>{value}</p>
    </div>
  );
}
