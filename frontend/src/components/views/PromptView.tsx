"use client";

import { useState } from "react";
import { AlertTriangle, Check, RotateCcw, Save, Sparkles } from "lucide-react";
import { errorMessage, promptAPI } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { useAppStore } from "@/lib/store";
import { humanize } from "@/lib/format";
import { Card, ErrorState, LoadingRows, PageHeader, SectionHeader } from "../ui";

interface PromptRecord {
  content: string;
  source: string;
  updated_by: string | null;
  updated_at: string | null;
}

interface PromptSuggestion {
  content: string;
  based_on: {
    regime: string;
    mood: string;
    india_vix: number | null;
    fii_trend: string;
    dii_trend: string;
    strong_sectors: string[];
    weak_sectors: string[];
  };
}

export default function PromptView() {
  const { toast } = useAppStore();
  const current = useApi<PromptRecord>(() => promptAPI.get(), []);
  const [draft, setDraft] = useState("");
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const [suggestion, setSuggestion] = useState<PromptSuggestion | null>(null);
  const [suggestError, setSuggestError] = useState("");

  // Uncontrolled until edited: show the live fetched content, then switch to the local draft.
  const value = dirty ? draft : current.data?.content ?? "";

  const save = async (content: string) => {
    setSaving(true);
    try {
      const res = await promptAPI.update(content);
      current.setData(res.data);
      setDraft(res.data.content);
      setDirty(false);
      setSuggestion(null);
      toast("Prompt saved", "success");
    } catch (e) {
      toast(errorMessage(e, "Could not save the prompt."), "error");
    } finally {
      setSaving(false);
    }
  };

  const suggest = async () => {
    setSuggesting(true);
    setSuggestError("");
    try {
      const res = await promptAPI.suggest();
      setSuggestion(res.data);
      setDraft(res.data.content);
      setDirty(true);
    } catch (e) {
      setSuggestError(errorMessage(e, "Could not generate a suggestion from live market data."));
    } finally {
      setSuggesting(false);
    }
  };

  const revert = () => {
    setDirty(false);
    setSuggestion(null);
  };

  return (
    <div className="space-y-5">
      <PageHeader
        title="AI Prompt"
        subtitle="The system prompt that steers AI-generated stock commentary. Edit it directly, or auto-suggest one from current market conditions."
      />

      {current.error && <ErrorState message={current.error} onRetry={current.reload} />}

      <Card>
        <SectionHeader
          icon={<Sparkles size={16} />}
          title="Current prompt"
          subtitle={
            current.data
              ? `Source: ${humanize(current.data.source)} · Updated by ${current.data.updated_by || "—"}${
                  current.data.updated_at ? ` · ${new Date(current.data.updated_at).toLocaleString("en-IN")}` : ""
                }`
              : undefined
          }
          actions={
            <button className="btn-secondary text-xs" style={{ padding: "6px 12px" }} onClick={suggest} disabled={suggesting}>
              <Sparkles size={13} className={suggesting ? "animate-pulse" : ""} />
              {suggesting ? "Reading market…" : "Suggest from market"}
            </button>
          }
        />

        {current.loading ? (
          <LoadingRows rows={6} />
        ) : (
          <>
            {suggestError && (
              <div className="mb-3">
                <ErrorState message={suggestError} />
              </div>
            )}

            {suggestion && (
              <div
                className="mb-4 p-3 rounded-lg text-xs"
                style={{ background: "rgba(99, 102, 241, 0.06)", border: "1px solid var(--border-subtle)" }}
              >
                <p className="font-semibold mb-2" style={{ color: "var(--text-primary)" }}>
                  Suggestion based on live conditions
                </p>
                <div className="flex flex-wrap gap-1.5">
                  <span className="badge badge-accent">{humanize(suggestion.based_on.regime)}</span>
                  <span className="badge badge-neutral">{humanize(suggestion.based_on.mood)} mood</span>
                  {suggestion.based_on.india_vix != null && (
                    <span className="badge badge-neutral">VIX {suggestion.based_on.india_vix.toFixed(1)}</span>
                  )}
                  {suggestion.based_on.fii_trend !== "neutral" && (
                    <span className="badge badge-neutral">FII {suggestion.based_on.fii_trend}</span>
                  )}
                  {suggestion.based_on.dii_trend !== "neutral" && (
                    <span className="badge badge-neutral">DII {suggestion.based_on.dii_trend}</span>
                  )}
                  {(suggestion.based_on.strong_sectors || []).map((s: string) => (
                    <span key={s} className="badge badge-bullish">{s}</span>
                  ))}
                  {(suggestion.based_on.weak_sectors || []).map((s: string) => (
                    <span key={s} className="badge badge-bearish">{s}</span>
                  ))}
                </div>
                <p className="mt-2" style={{ color: "var(--text-muted)" }}>
                  Review below, then save to make it the active prompt — nothing is applied until you save.
                </p>
              </div>
            )}

            <textarea
              value={value}
              onChange={(e) => {
                setDraft(e.target.value);
                setDirty(true);
              }}
              rows={16}
              className="w-full rounded-lg p-3 text-xs font-mono leading-relaxed"
              style={{
                background: "var(--bg-tertiary, rgba(255,255,255,0.03))",
                border: "1px solid var(--border-default)",
                color: "var(--text-primary)",
                resize: "vertical",
              }}
              spellCheck={false}
            />

            <div className="flex flex-wrap items-center justify-between gap-3 mt-4">
              <p className="text-[11px] flex items-center gap-1.5" style={{ color: "var(--text-muted)" }}>
                <AlertTriangle size={12} />
                Changes apply only after saving. This prompt guides AI commentary — it does not change the
                rule-based signal engine or ML predictions.
              </p>
              <div className="flex gap-2">
                <button className="btn-ghost text-xs" onClick={revert} disabled={!dirty || saving}>
                  <RotateCcw size={13} /> Revert
                </button>
                <button
                  className="btn-primary text-xs"
                  style={{ padding: "6px 14px" }}
                  onClick={() => save(value)}
                  disabled={!dirty || saving || !value.trim()}
                >
                  {saving ? <Check size={13} className="animate-pulse" /> : <Save size={13} />}
                  {saving ? "Saving…" : "Save prompt"}
                </button>
              </div>
            </div>
          </>
        )}
      </Card>
    </div>
  );
}
