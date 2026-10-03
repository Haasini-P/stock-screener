"use client";

/**
 * Simulated paper-trading order ticket for US stocks. Unlike OrderTicketDialog
 * (which places a REAL order against a linked broker account), this does NOT
 * touch any brokerage — it just inserts a row into this app's own paper-order
 * ledger. Fill price is entered by hand because there is no live US quote to
 * execute against yet (see backend/app/services/us_market/provider.py).
 */

import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, TrendingDown, TrendingUp } from "lucide-react";
import { errorMessage, paperTradingAPI, usMarketAPI } from "@/lib/api";
import { useAppStore } from "@/lib/store";
import { fmtINR, fmtUSD } from "@/lib/format";
import { Modal } from "./ui";

export default function PaperOrderDialog({
  open,
  onClose,
  symbol,
  side,
  onPlaced,
  defaultPrice,
  defaultQuantity,
}: {
  open: boolean;
  onClose: () => void;
  symbol: string;
  side: "BUY" | "SELL";
  onPlaced?: () => void;
  /** Pre-fills from a real source (e.g. the scanner's live quote) — the user
   * can still edit it; this never substitutes for a live price when none exists. */
  defaultPrice?: number | null;
  defaultQuantity?: number | null;
}) {
  // Modal unmounts its children when closed, so the form starts fresh on every open
  return (
    <Modal open={open} onClose={onClose} title={`Paper ${side === "BUY" ? "Buy" : "Sell"} ${symbol}`}>
      <PaperOrderForm symbol={symbol} side={side} onClose={onClose} onPlaced={onPlaced} defaultPrice={defaultPrice} defaultQuantity={defaultQuantity} />
    </Modal>
  );
}

function PaperOrderForm({
  symbol,
  side,
  onClose,
  onPlaced,
  defaultPrice,
  defaultQuantity,
}: {
  symbol: string;
  side: "BUY" | "SELL";
  onClose: () => void;
  onPlaced?: () => void;
  defaultPrice?: number | null;
  defaultQuantity?: number | null;
}) {
  const { toast } = useAppStore();
  const [quantity, setQuantity] = useState(String(defaultQuantity || 1));
  const [fillPrice, setFillPrice] = useState(defaultPrice ? String(defaultPrice) : "");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [placed, setPlaced] = useState(false);
  const [fxRate, setFxRate] = useState<number | null>(null);

  useEffect(() => {
    usMarketAPI.fxRate().then((res) => setFxRate(res.data.rate)).catch(() => setFxRate(null));
  }, []);

  const qtyNum = Number(quantity) || 0;
  const priceNum = Number(fillPrice) || 0;
  const orderValueUsd = qtyNum * priceNum;

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
          {fxRate && <> (≈ {fmtINR(Number(fillPrice) * fxRate, 0)}/share)</>}
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
          Paper trading only — simulated, no real brokerage call, no real money moves.
          {defaultPrice ? " Pre-filled with the latest live quote — edit if you want to practice a different fill." : " Enter the price you're practicing a fill at."}
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

      {orderValueUsd > 0 && (
        <div className="flex items-center justify-between text-xs p-2 rounded-lg" style={{ background: "rgba(255,255,255,0.02)", border: "1px solid var(--border-subtle)" }}>
          <span style={{ color: "var(--text-muted)" }}>Required amount</span>
          <span className="font-semibold tabular-nums" style={{ color: "var(--text-primary)" }}>
            {fmtUSD(orderValueUsd)}{fxRate && <span style={{ color: "var(--text-muted)", fontWeight: 400 }}> (≈ {fmtINR(orderValueUsd * fxRate, 0)})</span>}
          </span>
        </div>
      )}

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
