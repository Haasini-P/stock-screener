"use client";

/**
 * "Batch AI take" — one combined, cheaper Claude call covering several
 * stocks at once (a condensed verdict per stock, not the full 16-section
 * report). Triggered from the Scanner for the currently filtered rows.
 */

import { useEffect, useState } from "react";
import { Sparkles } from "lucide-react";
import { Modal } from "./ui";
import { aiAPI, AIBatchCommentaryResult, errorMessage } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import MarkdownContent from "./MarkdownContent";

export default function BatchAICommentary({
  open,
  onClose,
  symbols,
}: {
  open: boolean;
  onClose: () => void;
  symbols: string[];
}) {
  return (
    <Modal open={open} onClose={onClose} title={`AI quick scan — ${symbols.length} stocks`} maxWidth="max-w-2xl">
      {open && <BatchBody symbols={symbols} />}
    </Modal>
  );
}

function BatchBody({ symbols }: { symbols: string[] }) {
  const [loading, setLoading] = useState(true);
  const [result, setResult] = useState<AIBatchCommentaryResult | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    aiAPI
      .getBatchCommentary(symbols)
      .then((res) => !cancelled && setResult(res.data))
      .catch((err) => !cancelled && setError(errorMessage(err, "Could not generate the batch AI take.")))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div>
      <div className="flex items-center gap-1.5 text-xs mb-3" style={{ color: "var(--text-muted)" }}>
        <Sparkles size={12} style={{ color: "var(--accent-indigo)" }} />
        {symbols.join(", ")}
      </div>
      <div className="max-h-[65vh] overflow-y-auto pr-1">
        {loading ? (
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>Generating… (one combined call for all {symbols.length} stocks)</p>
        ) : error ? (
          <p className="text-xs" style={{ color: "var(--color-bearish)" }}>{error}</p>
        ) : result ? (
          <>
            <MarkdownContent content={result.content} />
            <p className="text-[10px] mt-3" style={{ color: "var(--text-muted)" }}>
              {result.model}{result.cached ? " · cached" : ""} · {timeAgo(result.generated_at)}
            </p>
          </>
        ) : null}
      </div>
    </div>
  );
}
