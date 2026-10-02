"use client";

/**
 * "AI take" affordance — collapsed button that, on click, generates (or
 * returns already-cached) Claude commentary for a stock. Used on the
 * Scanner, Daily Signals and Stock Report. Never fires automatically.
 */

import { useState } from "react";
import { BarChart3, Sparkles } from "lucide-react";
import { aiAPI, AICommentaryResult, errorMessage } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import MarkdownContent from "./MarkdownContent";

export default function AICommentary({ symbol }: { symbol: string }) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AICommentaryResult | null>(null);
  const [error, setError] = useState("");

  const run = async () => {
    setOpen(true);
    if (result || loading) return;
    setLoading(true);
    setError("");
    try {
      const res = await aiAPI.getCommentary(symbol);
      setResult(res.data);
    } catch (err) {
      setError(errorMessage(err, "Could not generate AI commentary."));
    } finally {
      setLoading(false);
    }
  };

  if (!open) {
    return (
      <button className="btn-ghost text-xs" style={{ padding: "4px 8px" }} onClick={run} title={`Generate an AI take on ${symbol}`}>
        <Sparkles size={12} /> AI take
      </button>
    );
  }

  return (
    <div className="p-3 rounded-lg" style={{ background: "rgba(99, 102, 241, 0.05)", border: "1px solid var(--border-subtle)" }}>
      <div className="flex items-center gap-1.5 text-xs font-semibold" style={{ color: "var(--text-primary)" }}>
        <Sparkles size={12} style={{ color: "var(--accent-indigo)" }} /> AI take on {symbol}
      </div>
      {loading ? (
        <p className="text-xs mt-2" style={{ color: "var(--text-muted)" }}>Generating… (this can take a while for a full report)</p>
      ) : error ? (
        <p className="text-xs mt-2" style={{ color: "var(--color-bearish)" }}>{error}</p>
      ) : result ? (
        <>
          <div className="mt-2">
            <MarkdownContent content={result.content} />
          </div>
          <p className="text-[10px] mt-2 flex items-center gap-2" style={{ color: "var(--text-muted)" }}>
            <span>{result.model}{result.cached ? " · cached" : ""} · {timeAgo(result.generated_at)}</span>
            {result.chart_included && (
              <span className="inline-flex items-center gap-1"><BarChart3 size={10} /> chart analyzed</span>
            )}
          </p>
        </>
      ) : null}
    </div>
  );
}
