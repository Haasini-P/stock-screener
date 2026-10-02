"use client";

/**
 * Create-alert dialog, used from the Alerts view and stock pages.
 */

import { useState } from "react";
import Link from "next/link";
import { BellPlus } from "lucide-react";
import { alertsAPI, AlertType, errorMessage } from "@/lib/api";
import { useAppStore } from "@/lib/store";
import { Modal } from "./ui";

export const ALERT_TYPES: { value: AlertType; label: string; unit: string }[] = [
  { value: "signal_buy", label: "Notify me on a BUY signal", unit: "" },
  { value: "price_above", label: "Price rises above", unit: "₹" },
  { value: "price_below", label: "Price falls below", unit: "₹" },
  { value: "change_above", label: "Day change above", unit: "%" },
  { value: "change_below", label: "Day change below", unit: "%" },
];

export default function AlertDialog({
  open,
  onClose,
  symbol = "",
  currentPrice,
  defaultType = "price_above",
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  symbol?: string;
  currentPrice?: number | null;
  defaultType?: AlertType;
  onCreated?: () => void;
}) {
  const { isAuthenticated } = useAppStore();
  // Modal unmounts its children when closed, so the form starts fresh on every open
  return (
    <Modal open={open} onClose={onClose} title="Create alert">
      {!isAuthenticated ? (
        <div className="text-xs space-y-3" style={{ color: "var(--text-secondary)" }}>
          <p>Alerts are saved to your account so they can be checked against live prices and signals.</p>
          <Link href="/login?next=%2F%23alerts" className="btn-primary text-xs inline-flex">
            Sign in to create alerts
          </Link>
        </div>
      ) : (
        <AlertForm initialSymbol={symbol} currentPrice={currentPrice} defaultType={defaultType} onClose={onClose} onCreated={onCreated} />
      )}
    </Modal>
  );
}

function AlertForm({
  initialSymbol,
  currentPrice,
  defaultType,
  onClose,
  onCreated,
}: {
  initialSymbol: string;
  currentPrice?: number | null;
  defaultType: AlertType;
  onClose: () => void;
  onCreated?: () => void;
}) {
  const { toast } = useAppStore();
  const [symbol, setSymbol] = useState(initialSymbol);
  const [type, setType] = useState<AlertType>(defaultType);
  const [value, setValue] = useState(currentPrice ? String(Math.round(currentPrice * 1.05)) : "");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const needsValue = type !== "signal_buy";

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!symbol.trim()) return setError("Enter a stock symbol.");
    let num: number | undefined;
    if (needsValue) {
      num = parseFloat(value);
      if (Number.isNaN(num)) return setError("Enter a numeric value.");
    }
    setSaving(true);
    setError("");
    try {
      await alertsAPI.create({ symbol: symbol.trim().toUpperCase(), alert_type: type, value: num, message: message || undefined });
      toast(`Alert created for ${symbol.toUpperCase()}`, "success");
      onCreated?.();
      onClose();
    } catch (err) {
      setError(errorMessage(err, "Could not create alert."));
    } finally {
      setSaving(false);
    }
  };

  const unit = ALERT_TYPES.find((t) => t.value === type)?.unit;

  return (
    <form onSubmit={submit} className="space-y-3">
      <div>
        <label className="field-label" htmlFor="alert-symbol">Symbol</label>
        <input
          id="alert-symbol"
          className="input font-mono uppercase"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          placeholder="RELIANCE"
          required
        />
      </div>
      <div className={needsValue ? "grid grid-cols-2 gap-3" : ""}>
        <div>
          <label className="field-label" htmlFor="alert-type">Condition</label>
          <select id="alert-type" className="input" value={type} onChange={(e) => setType(e.target.value as AlertType)}>
            {ALERT_TYPES.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </div>
        {needsValue && (
          <div>
            <label className="field-label" htmlFor="alert-value">Value ({unit})</label>
            <input
              id="alert-value"
              className="input"
              type="number"
              step="any"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              required
            />
          </div>
        )}
      </div>
      {type === "signal_buy" && (
        <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
          Fires the next time this stock&apos;s computed signal becomes BUY NOW, BUY ON RETEST or BUY ON DIP — the notification includes the entry zone, stop loss and target at that moment.
        </p>
      )}
      <div>
        <label className="field-label" htmlFor="alert-note">Note (optional)</label>
        <input id="alert-note" className="input" value={message} onChange={(e) => setMessage(e.target.value)} maxLength={500} />
      </div>
      {needsValue && currentPrice != null && (
        <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>Current price: ₹{currentPrice.toLocaleString("en-IN")}</p>
      )}
      {error && <p className="text-xs" style={{ color: "var(--color-bearish)" }}>{error}</p>}
      <div className="flex justify-end gap-2 pt-1">
        <button type="button" className="btn-secondary text-xs" onClick={onClose}>Cancel</button>
        <button type="submit" className="btn-primary text-xs" disabled={saving}>
          <BellPlus size={14} /> {saving ? "Saving…" : "Create alert"}
        </button>
      </div>
    </form>
  );
}
