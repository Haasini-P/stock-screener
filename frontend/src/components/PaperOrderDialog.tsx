"use client";

/**
 * Simulated paper-trading order ticket for US stocks. Unlike OrderTicketDialog
 * (which places a REAL order against a linked broker account), this does NOT
 * touch any brokerage — it just inserts a row into this app's own paper-order
 * ledger. Fill price is entered by hand because there is no live US quote to
 * execute against yet (see backend/app/services/us_market/provider.py).
 */

import { useState } from "react";
import { AlertTriangle, CheckCircle2, TrendingDown, TrendingUp } from "lucide-react";
import { errorMessage, paperTradingAPI } from "@/lib/api";
import { useAppStore } from "@/lib/store";
import { fmtUSD } from "@/lib/format";
import { Modal } from "./ui";

export default function PaperOrderDialog({
  open,
  onClose,
  symbol,
  side,
  onPlaced,
}: {
  open: boolean;
  onClose: () => void;
  symbol: string;
  side: "BUY" | "SELL";
  onPlaced?: () => void;
}) {
  // Modal unmounts its children when closed, so the form starts fresh on every open
  return (
    <Modal open={open} onClose={onClose} title={`Paper ${side === "BUY" ? "Buy" : "Sell"} ${symbol}`}>
      <PaperOrderForm symbol={symbol} side={side} onClose={onClose} onPlaced={onPlaced} />
    </Modal>
  );
}

function PaperOrderForm({
  symbol,
  side,
  onClose,
  onPlaced,
}: {
  symbol: string;
  side: "BUY" | "SELL";
  onClose: () => void;
  onPlaced?: () => void;
}) {
  const { toast } = useAppStore();
  const [quantity, setQuantity] = useState("1");
  const [fillPrice, setFillPrice] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [placed, setPlaced] = useState(false);

  const submit = async () => {
    setError("");
    const qty = Number(quantity);
    const price = Number(fillPrice);
    if (!qty || qty <= 0) return setError("Enter a quantity greater than 0.");
    if (!price || price <= 0) return setError("Enter the price you're paper-filling at.");

    setSaving(true);
    try {
      await paperTradingAPI.placeOrder({ symbol, side, quantity: qty, fill_price: price, notes: notes || undefined });
      setPlaced(true);
      toast(`Paper ${side.toLowerCase()} recorded for ${symbol}`, "success");
      onPlaced?.();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  if (placed) {
    return (
      <div className="text-center py-4 space-y-3">
        <CheckCircle2 size={32} className="mx-auto text-bullish" />
        <p className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
          Paper {side === "BUY" ? "buy" : "sell"} recorded
        </p>
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
          {quantity} shares of {symbol} at {fmtUSD(Number(fillPrice))} — simulated only.
        </p>
        <button className="btn-primary text-xs" onClick={onClose}>Close</button>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-start gap-2 p-2.5 rounded-lg text-[11px]" style={{ background: "rgba(99,102,241,0.08)", color: "var(--text-secondary)" }}>
        <AlertTriangle size={13} style={{ flexShrink: 0, marginTop: 1 }} />
        <span>
          Paper trading only — simulated, no real brokerage call. StockMind has no live US quote
          yet, so enter the price you&apos;re practicing a fill at.
        </span>
      </div>

      <div>
        <label className="field-label">Quantity</label>
        <input type="number" min="1" step="1" className="input" value={quantity} onChange={(e) => setQuantity(e.target.value)} />
      </div>
      <div>
        <label className="field-label">Fill price (USD)</label>
        <input type="number" min="0" step="0.01" className="input" placeholder="0.00" value={fillPrice} onChange={(e) => setFillPrice(e.target.value)} />
      </div>
      <div>
        <label className="field-label">Notes (optional)</label>
        <input type="text" className="input" maxLength={255} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </div>

      {error && <p className="text-xs text-bearish">{error}</p>}

      <div className="flex gap-2 pt-1">
        <button className="btn-secondary text-xs flex-1" onClick={onClose} disabled={saving}>Cancel</button>
        <button
          className="btn-primary text-xs flex-1"
          style={side === "SELL" ? { background: "var(--color-bearish)" } : undefined}
          onClick={submit}
          disabled={saving}
        >
          {side === "BUY" ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
          {saving ? "Recording…" : `Record paper ${side === "BUY" ? "buy" : "sell"}`}
        </button>
      </div>
    </div>
  );
}
