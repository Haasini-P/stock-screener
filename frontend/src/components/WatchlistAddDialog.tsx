"use client";

/**
 * Manually track any symbol on the scanner's watchlist — regardless of
 * whether it currently passes the live technical screen — with a chosen
 * short/mid/long holding-period classification.
 */

import { useState } from "react";
import { Modal } from "./ui";
import SearchBox from "./SearchBox";
import { errorMessage, watchlistAPI, WatchlistTerm } from "@/lib/api";
import { useAppStore } from "@/lib/store";

const TERM_OPTIONS: { value: WatchlistTerm; label: string; hint: string }[] = [
  { value: "short", label: "Short term", hint: "days to ~2 weeks" },
  { value: "mid", label: "Mid term", hint: "weeks to a couple months" },
  { value: "long", label: "Long term", hint: "months, riding the larger trend" },
];

export default function WatchlistAddDialog({ open, onClose, onAdded }: { open: boolean; onClose: () => void; onAdded: () => void }) {
  return (
    <Modal open={open} onClose={onClose} title="Add to watchlist">
      {open && <AddForm onClose={onClose} onAdded={onAdded} />}
    </Modal>
  );
}

function AddForm({ onClose, onAdded }: { onClose: () => void; onAdded: () => void }) {
  const { toast } = useAppStore();
  const [symbol, setSymbol] = useState("");
  const [term, setTerm] = useState<WatchlistTerm>("mid");
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    if (!symbol) return toast("Pick a stock first", "info");
    setSaving(true);
    try {
      await watchlistAPI.add(symbol, term);
      toast(`${symbol} added to watchlist (${term} term)`, "success");
      onAdded();
      onClose();
    } catch (err) {
      toast(errorMessage(err, "Could not add to watchlist."), "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <label className="field-label">Stock</label>
        {symbol ? (
          <div className="flex items-center justify-between input">
            <span className="font-semibold">{symbol}</span>
            <button className="btn-ghost text-xs" onClick={() => setSymbol("")}>Change</button>
          </div>
        ) : (
          <SearchBox onSelect={setSymbol} autoFocus />
        )}
      </div>
      <div>
        <label className="field-label">Holding period</label>
        <div className="space-y-1.5">
          {TERM_OPTIONS.map((t) => (
            <label
              key={t.value}
              className="flex items-center gap-2 p-2 rounded-lg cursor-pointer text-xs"
              style={{ border: `1px solid ${term === t.value ? "var(--accent-indigo)" : "var(--border-subtle)"}`, background: term === t.value ? "rgba(99,102,241,0.08)" : "transparent" }}
            >
              <input type="radio" name="term" checked={term === t.value} onChange={() => setTerm(t.value)} />
              <span className="font-semibold" style={{ color: "var(--text-primary)" }}>{t.label}</span>
              <span style={{ color: "var(--text-muted)" }}>· {t.hint}</span>
            </label>
          ))}
        </div>
      </div>
      <div className="flex justify-end gap-2">
        <button className="btn-secondary text-xs" onClick={onClose}>Cancel</button>
        <button className="btn-primary text-xs" style={{ padding: "7px 14px" }} onClick={submit} disabled={saving || !symbol}>
          {saving ? "Adding…" : "Add to watchlist"}
        </button>
      </div>
    </div>
  );
}
