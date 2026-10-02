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

export function EntryBadge({ entry }: { entry: string | null | undefined }) {
  if (!entry) return <span className="text-muted">—</span>;
  return <span className={`badge ${ENTRY_STYLE[entry] || "badge-neutral"}`}>{humanize(entry.toLowerCase())}</span>;
}

export function BucketChips({ buckets }: { buckets: string[] | undefined }) {
  if (!buckets?.length) return <span className="text-muted">—</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {buckets.map((b) => (
        <span key={b} className="badge badge-accent" style={{ fontSize: 9 }}>{humanize(b)}</span>
      ))}
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
