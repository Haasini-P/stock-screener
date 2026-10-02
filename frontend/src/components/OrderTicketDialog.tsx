"use client";

/**
 * Live order-ticket dialog, opened from Buy/Sell actions on the Market
 * Scanner and the Stock Report. This places a REAL order against a linked
 * broker account — there is no paper-trading mode.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronUp, TrendingDown, TrendingUp } from "lucide-react";
import { accountsAPI, BrokerAccount, errorMessage, OrderSide, ordersAPI } from "@/lib/api";
import { useAppStore } from "@/lib/store";
import { fmtNum } from "@/lib/format";
import { Modal } from "./ui";

export interface OrderDefaults {
  quantity?: number | null;
  price?: number | null;
  product?: "DELIVERY" | "INTRADAY";
  target?: number | null;
  stopLoss?: number | null;
}

export default function OrderTicketDialog({
  open,
  onClose,
  symbol,
  side,
  defaults,
}: {
  open: boolean;
  onClose: () => void;
  symbol: string;
  side: OrderSide;
  defaults?: OrderDefaults;
}) {
  const { isAuthenticated } = useAppStore();
  // Modal unmounts its children when closed, so the form starts fresh on every open
  return (
    <Modal open={open} onClose={onClose} title={`${side === "BUY" ? "Buy" : "Sell"} ${symbol}`}>
      {!isAuthenticated ? (
        <div className="text-xs space-y-3" style={{ color: "var(--text-secondary)" }}>
          <p>Sign in and link a broker account to place live orders.</p>
          <Link href="/login?next=%2F%23report" className="btn-primary text-xs inline-flex">
            Sign in
          </Link>
        </div>
      ) : (
        <OrderForm symbol={symbol} side={side} defaults={defaults} onClose={onClose} />
      )}
    </Modal>
  );
}

function OrderForm({
  symbol,
  side,
  defaults,
  onClose,
}: {
  symbol: string;
  side: OrderSide;
  defaults?: OrderDefaults;
  onClose: () => void;
}) {
  const { toast } = useAppStore();
  const [accounts, setAccounts] = useState<BrokerAccount[] | null>(null);
  const [accountsError, setAccountsError] = useState("");
  const [accountId, setAccountId] = useState("");
  const [transactionType, setTransactionType] = useState<OrderSide>(side);
  const [orderType, setOrderType] = useState<"MARKET" | "LIMIT">(defaults?.price ? "LIMIT" : "MARKET");
  const [quantity, setQuantity] = useState(String(defaults?.quantity || 1));
  const [price, setPrice] = useState(defaults?.price ? String(defaults.price) : "");
  const [product, setProduct] = useState<"DELIVERY" | "INTRADAY">(defaults?.product || "DELIVERY");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [placed, setPlaced] = useState<{ order_id: string | null; status: string; account_nickname: string; bracket_placed?: boolean } | null>(null);

  const [bracketOpen, setBracketOpen] = useState(!!(defaults?.target || defaults?.stopLoss));
  const [targetPrice, setTargetPrice] = useState(defaults?.target ? String(defaults.target) : "");
  const [stopPrice, setStopPrice] = useState(defaults?.stopLoss ? String(defaults.stopLoss) : "");
  const [trailingEnabled, setTrailingEnabled] = useState(false);
  const [trailingAmount, setTrailingAmount] = useState("");

  useEffect(() => {
    accountsAPI
      .list()
      .then((res) => {
        setAccounts(res.data);
        const active = res.data.find((a) => a.is_active && a.is_connected) || res.data.find((a) => a.is_connected);
        if (active) setAccountId(active.id);
      })
      .catch((err) => setAccountsError(errorMessage(err, "Could not load linked accounts.")));
  }, []);

  const connectedAccounts = (accounts || []).filter((a) => a.is_connected);
  const selected = connectedAccounts.find((a) => a.id === accountId);

  const needsPrice = orderType === "LIMIT" || bracketOpen;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const qty = parseInt(quantity, 10);
    const priceNum = price ? parseFloat(price) : undefined;
    if (!accountId) return setError("Choose an account to place this order on.");
    if (!(qty > 0)) return setError("Enter a quantity greater than 0.");
    if (needsPrice && !(priceNum && priceNum > 0)) {
      return setError(bracketOpen ? "A target/stop-loss bracket needs an entry price." : "Enter a limit price.");
    }

    let targetNum: number | undefined;
    let stopNum: number | undefined;
    let trailNum: number | undefined;
    if (bracketOpen) {
      targetNum = parseFloat(targetPrice);
      stopNum = parseFloat(stopPrice);
      if (!(targetNum > 0) || !(stopNum > 0)) return setError("Enter both a target price and a stop-loss price.");
      const ok = transactionType === "BUY" ? stopNum < priceNum! && priceNum! < targetNum : targetNum < priceNum! && priceNum! < stopNum;
      if (!ok) {
        return setError(
          transactionType === "BUY"
            ? "For a Buy bracket: stop-loss must be below entry price, which must be below target."
            : "For a Sell bracket: target must be below entry price, which must be below stop-loss."
        );
      }
      if (trailingEnabled) {
        trailNum = parseFloat(trailingAmount);
        if (!(trailNum > 0)) return setError("Enter a trailing gap greater than 0.");
      }
    }

    setSaving(true);
    setError("");
    try {
      const res = await ordersAPI.place({
        account_id: accountId,
        symbol,
        transaction_type: transactionType,
        quantity: qty,
        order_type: orderType,
        product,
        price: priceNum,
        target_price: targetNum,
        stop_price: stopNum,
        trailing_amount: trailNum,
      });
      setPlaced(res.data);
      toast(`${transactionType === "BUY" ? "Buy" : "Sell"} order placed for ${symbol}`, "success");
    } catch (err) {
      setError(errorMessage(err, "The broker rejected this order."));
    } finally {
      setSaving(false);
    }
  };

  if (placed) {
    return (
      <div className="space-y-4">
        <div className="flex items-start gap-3 p-3 rounded-lg" style={{ background: "var(--color-bullish-bg)", border: "1px solid var(--color-bullish-border)" }}>
          <CheckCircle2 size={18} style={{ color: "var(--color-bullish)", flexShrink: 0, marginTop: 1 }} />
          <div className="text-xs">
            <p className="font-semibold" style={{ color: "var(--text-primary)" }}>Order submitted to {placed.account_nickname}</p>
            <p style={{ color: "var(--text-secondary)" }}>Status: {placed.status}{placed.order_id ? ` · Order ID ${placed.order_id}` : ""}</p>
            {placed.bracket_placed && <p style={{ color: "var(--text-secondary)" }}>Target/stop-loss bracket placed — see it under Portfolio → Active Brackets.</p>}
          </div>
        </div>
        <div className="flex justify-end">
          <button type="button" className="btn-primary text-xs" onClick={onClose}>Done</button>
        </div>
      </div>
    );
  }

  if (accountsError) {
    return <p className="text-xs" style={{ color: "var(--color-bearish)" }}>{accountsError}</p>;
  }

  if (accounts && connectedAccounts.length === 0) {
    return (
      <div className="text-xs space-y-3" style={{ color: "var(--text-secondary)" }}>
        <p>No connected broker account yet. Link an Upstox or Kite account to place live orders.</p>
        <Link href="/#settings" onClick={onClose} className="btn-primary text-xs inline-flex">
          Go to Settings → Accounts
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <div
        className="flex items-start gap-2 p-2.5 rounded-lg text-[11px]"
        style={{ background: "var(--color-bearish-bg)", border: "1px solid var(--color-bearish-border)", color: "var(--text-primary)" }}
      >
        <AlertTriangle size={14} style={{ color: "var(--color-bearish)", flexShrink: 0, marginTop: 1 }} />
        <span>
          This places a <strong>real order</strong> on {selected ? `${selected.nickname || selected.provider} (${selected.provider})` : "the selected account"}. It is not simulated.
        </span>
      </div>

      <div>
        <label className="field-label" htmlFor="order-account">Account</label>
        <select id="order-account" className="input" value={accountId} onChange={(e) => setAccountId(e.target.value)} required>
          {!accounts && <option value="">Loading accounts…</option>}
          {connectedAccounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.nickname || a.provider} ({a.provider}){a.is_active ? " · active" : ""}
            </option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="field-label">Side</label>
          <div className="flex gap-2">
            <button
              type="button"
              className={`chip flex-1 justify-center ${transactionType === "BUY" ? "chip-active" : ""}`}
              style={transactionType === "BUY" ? { color: "var(--color-bullish)" } : undefined}
              onClick={() => setTransactionType("BUY")}
            >
              <TrendingUp size={13} /> Buy
            </button>
            <button
              type="button"
              className={`chip flex-1 justify-center ${transactionType === "SELL" ? "chip-active" : ""}`}
              style={transactionType === "SELL" ? { color: "var(--color-bearish)" } : undefined}
              onClick={() => setTransactionType("SELL")}
            >
              <TrendingDown size={13} /> Sell
            </button>
          </div>
        </div>
        <div>
          <label className="field-label" htmlFor="order-product">Product</label>
          <select id="order-product" className="input" value={product} onChange={(e) => setProduct(e.target.value as typeof product)}>
            <option value="DELIVERY">Delivery</option>
            <option value="INTRADAY">Intraday</option>
          </select>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="field-label" htmlFor="order-type">Order type</label>
          <select id="order-type" className="input" value={orderType} onChange={(e) => setOrderType(e.target.value as typeof orderType)}>
            <option value="MARKET">Market</option>
            <option value="LIMIT">Limit</option>
          </select>
        </div>
        <div>
          <label className="field-label" htmlFor="order-qty">Quantity</label>
          <input id="order-qty" className="input" type="number" min={1} step={1} value={quantity} onChange={(e) => setQuantity(e.target.value)} required />
        </div>
      </div>

      {needsPrice && (
        <div>
          <label className="field-label" htmlFor="order-price">
            {orderType === "LIMIT" ? "Limit price (₹)" : "Entry price (₹)"}
          </label>
          <input id="order-price" className="input" type="number" min={0} step="0.05" value={price} onChange={(e) => setPrice(e.target.value)} required />
          {orderType === "MARKET" && (
            <p className="text-[10px] mt-1" style={{ color: "var(--text-muted)" }}>
              A bracket needs a fixed reference price — this is sent as an immediate limit entry, not a true market order.
            </p>
          )}
        </div>
      )}

      {defaults?.price != null && (
        <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>Reference entry: ₹{fmtNum(defaults.price)}</p>
      )}

      <div className="rounded-lg" style={{ border: "1px solid var(--border-subtle)" }}>
        <button
          type="button"
          className="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold"
          style={{ color: "var(--text-primary)" }}
          onClick={() => setBracketOpen((v) => !v)}
        >
          Add target &amp; stop-loss
          {bracketOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
        {bracketOpen && (
          <div className="px-3 pb-3 space-y-3 border-t" style={{ borderColor: "var(--border-subtle)" }}>
            <div className="grid grid-cols-2 gap-3 pt-3">
              <div>
                <label className="field-label" htmlFor="order-target">Target (₹)</label>
                <input id="order-target" className="input" type="number" min={0} step="0.05" value={targetPrice} onChange={(e) => setTargetPrice(e.target.value)} />
              </div>
              <div>
                <label className="field-label" htmlFor="order-stop">Stop-loss (₹)</label>
                <input id="order-stop" className="input" type="number" min={0} step="0.05" value={stopPrice} onChange={(e) => setStopPrice(e.target.value)} />
              </div>
            </div>
            <div>
              <label className="flex items-center gap-2 text-xs" style={{ color: "var(--text-secondary)" }}>
                <input type="checkbox" checked={trailingEnabled} onChange={(e) => setTrailingEnabled(e.target.checked)} />
                Trailing stop-loss
              </label>
              {trailingEnabled && (
                <input
                  className="input mt-2"
                  type="number"
                  min={0}
                  step="0.05"
                  placeholder="Trailing gap (₹)"
                  value={trailingAmount}
                  onChange={(e) => setTrailingAmount(e.target.value)}
                />
              )}
            </div>
            <p className="text-[10px]" style={{ color: "var(--text-muted)" }}>
              {selected?.provider === "kite"
                ? trailingEnabled
                  ? "Kite has no native trailing stop-loss — StockMind checks the price roughly every minute and raises your stop while its backend is running. It stops advancing if the server is down."
                  : "Placed as a single OCO order on Kite — whichever of target or stop-loss is hit first cancels the other."
                : "Upstox places this as one GTT order. Trailing (if enabled) is handled by Upstox itself — it keeps working even if StockMind isn't running."}
            </p>
          </div>
        )}
      </div>

      {error && <p className="text-xs" style={{ color: "var(--color-bearish)" }}>{error}</p>}

      <div className="flex justify-end gap-2 pt-1">
        <button type="button" className="btn-secondary text-xs" onClick={onClose}>Cancel</button>
        <button type="submit" className="btn-primary text-xs" disabled={saving || !accounts}>
          {saving ? "Placing order…" : `Confirm & place ${transactionType === "BUY" ? "buy" : "sell"} order`}
        </button>
      </div>
    </form>
  );
}
