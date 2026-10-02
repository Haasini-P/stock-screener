"use client";

import { useRef, useState } from "react";
import { AlertTriangle, BellPlus, PiggyBank, Settings as SettingsIcon, Shield, Zap } from "lucide-react";
import { signalsAPI } from "@/lib/api";
import { portfolioParams, useAppStore } from "@/lib/store";
import { useApi } from "@/lib/useApi";
import { fmtINR, fmtNum, humanize } from "@/lib/format";
import AICommentary from "../AICommentary";
import AlertDialog from "../AlertDialog";
import { useNavigateTab } from "../AppShell";
import { BucketChips, Card, Change, EmptyState, EntryBadge, ErrorState, KeyValue, LoadingRows, PageHeader, RefreshButton, StockLink } from "../ui";
import { regimeColor } from "./DashboardView";

const HORIZONS = [
  { key: "short_term", label: "Short term", hint: "1–4 weeks" },
  { key: "mid_term", label: "Mid term", hint: "1–6 months" },
  { key: "long_term", label: "Long term", hint: "6–24 months" },
] as const;

const GROUPS = [
  { key: "buy_now", label: "🟢 Buy now" },
  { key: "watch_retest", label: "🟡 Watch / retest" },
  { key: "wait", label: "🟠 Wait" },
  { key: "avoid", label: "🔴 Avoid" },
] as const;

function SignalTable({ rows, showSizing, onAlert }: { rows: any[]; showSizing: boolean; onAlert: (symbol: string) => void }) {
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <th>Stock</th><th>Signal</th><th>CMP</th><th>Entry zone</th><th>Stop loss</th><th>Target 1</th><th>Target 2</th>
            <th>R:R</th><th>P(up)</th>{showSizing && <><th>Qty</th><th>Value</th><th>Risk</th></>}<th>Setups</th><th>AI</th><th>Alert</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((s) => (
            <tr key={s.symbol} title={s.explanation || undefined}>
              <td>
                <StockLink symbol={s.symbol} />
                <div className="text-[10px]" style={{ color: "var(--text-muted)" }}>{s.sector} · {s.trend}</div>
              </td>
              <td><EntryBadge entry={s.entry} />{s.continuity === "NEW" && <span className="badge badge-accent ml-1" style={{ fontSize: 9 }}>New</span>}</td>
              <td className="tabular-nums">{fmtINR(s.ltp)}<div><Change value={s.change_pct} className="text-[10px]" /></div></td>
              <td className="tabular-nums text-xs whitespace-nowrap">{s.entry_zone ? `${fmtNum(s.entry_zone[0])} – ${fmtNum(s.entry_zone[1])}` : "—"}</td>
              <td className="tabular-nums" style={{ color: "var(--color-bearish)" }}>{fmtINR(s.stop_loss)}</td>
              <td className="tabular-nums" style={{ color: "var(--color-bullish)" }}>{fmtINR(s.target_1)}</td>
              <td className="tabular-nums" style={{ color: "var(--color-bullish)" }}>{fmtINR(s.target_2)}</td>
              <td className="tabular-nums">{s.risk_reward ? `${s.risk_reward}:1` : "—"}</td>
              <td className="tabular-nums">{s.probability_up != null ? `${(s.probability_up * 100).toFixed(0)}%` : "—"}</td>
              {showSizing && (
                <>
                  <td className="tabular-nums">{s.quantity ?? "—"}</td>
                  <td className="tabular-nums">{fmtINR(s.position_value, 0)}</td>
                  <td className="tabular-nums">{fmtINR(s.max_risk, 0)}</td>
                </>
              )}
              <td><BucketChips buckets={s.buckets} /></td>
              <td><AICommentary symbol={s.symbol} /></td>
              <td>
                <button className="btn-ghost text-xs" style={{ padding: "4px 6px" }} onClick={() => onAlert(s.symbol)} title={`Notify me when ${s.symbol} becomes a BUY signal`}>
                  <BellPlus size={13} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function SignalsView() {
  const { settings } = useAppStore();
  const navigate = useNavigateTab();
  const [horizon, setHorizon] = useState<(typeof HORIZONS)[number]["key"]>("short_term");
  const [group, setGroup] = useState<(typeof GROUPS)[number]["key"]>("watch_retest");
  const [view, setView] = useState<"horizon" | "action">("horizon");
  const [rebuilds, setRebuilds] = useState(0);
  const [alertSymbol, setAlertSymbol] = useState<string | null>(null);
  const refreshNext = useRef(false);

  const daily = useApi(() => {
    const refresh = refreshNext.current;
    refreshNext.current = false;
    return signalsAPI.dailyList(portfolioParams(settings), refresh);
  }, [settings.capital, settings.riskPct, rebuilds]);

  const d = daily.data;
  const deploy = d?.capital_deployment;
  const regime = d?.market_regime;
  const rows: any[] = d ? (view === "horizon" ? d.stocks[horizon] : d.actionable[group]) : [];

  return (
    <div className="space-y-5">
      <PageHeader
        title="Daily Stock Signals"
        subtitle={d ? `Report for ${d.date} · ${d.screener?.analyzed ?? 0} stocks screened · regime ${regime?.regime}` : "Multi-bucket discovery across the approved sector universe"}
        actions={
          <RefreshButton
            onClick={() => {
              refreshNext.current = true;
              setRebuilds((n) => n + 1);
            }}
            busy={daily.loading || daily.refreshing}
            label="Regenerate"
            updatedAt={daily.updatedAt}
          />
        }
      />

      {daily.error && <ErrorState message={daily.error} onRetry={daily.reload} />}

      {/* Deployment & regime */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <Card className="lg:col-span-2" accent={regimeColor(regime?.regime)}>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <PiggyBank size={16} style={{ color: "var(--accent-indigo)" }} />
              <h3 className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>Capital Deployment</h3>
            </div>
            <button className="btn-ghost text-xs" onClick={() => navigate("settings")}>
              <SettingsIcon size={13} /> Capital & risk settings
            </button>
          </div>
          {deploy ? (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <KeyValue label="Total capital" value={fmtINR(deploy.total_capital, 0)} />
                <KeyValue label={`Deploy (${deploy.suggested_deployment_pct}%)`} value={fmtINR(deploy.deployable_amount, 0)} valueColor="var(--color-bullish)" />
                <KeyValue label="Cash reserve" value={fmtINR(deploy.cash_reserve, 0)} />
                <KeyValue label="Max risk / trade" value={fmtINR(deploy.max_risk_per_trade, 0)} valueColor="var(--color-bearish)" />
              </div>
              <p className="text-[11px] mt-4" style={{ color: "var(--text-muted)" }}>
                {deploy.note} {deploy.sector_diversification}.
              </p>
            </>
          ) : (
            <LoadingRows rows={2} />
          )}
        </Card>

        <Card>
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle size={16} style={{ color: "var(--color-neutral)" }} />
            <h3 className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>Risk Alerts</h3>
          </div>
          {!d ? (
            <LoadingRows rows={2} />
          ) : d.risk_alerts.length === 0 ? (
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>No active market risk alerts.</p>
          ) : (
            <ul className="space-y-3">
              {d.risk_alerts.map((a: any, i: number) => (
                <li key={i} className="text-xs">
                  <p className="font-semibold" style={{ color: "var(--color-bearish)" }}>{a.trigger}</p>
                  <p style={{ color: "var(--text-secondary)" }}>{a.impact}</p>
                  <p style={{ color: "var(--text-muted)" }}>Action: {a.action}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      {/* Lists */}
      <Card padded={false}>
        <div className="px-5 pt-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex gap-2">
            <button className={`chip ${view === "horizon" ? "chip-active" : ""}`} onClick={() => setView("horizon")}>By horizon</button>
            <button className={`chip ${view === "action" ? "chip-active" : ""}`} onClick={() => setView("action")}>By action</button>
          </div>
          <div className="flex flex-wrap gap-2">
            {view === "horizon"
              ? HORIZONS.map((h) => (
                  <button key={h.key} className={`chip ${horizon === h.key ? "chip-active" : ""}`} onClick={() => setHorizon(h.key)} title={h.hint}>
                    {h.label} <span className="opacity-60">({d?.stocks[h.key].length ?? 0})</span>
                  </button>
                ))
              : GROUPS.map((g) => (
                  <button key={g.key} className={`chip ${group === g.key ? "chip-active" : ""}`} onClick={() => setGroup(g.key)}>
                    {g.label} <span className="opacity-60">({d?.actionable[g.key].length ?? 0})</span>
                  </button>
                ))}
          </div>
        </div>
        <div className="p-3">
          {daily.loading ? (
            <div className="p-2"><LoadingRows rows={6} /></div>
          ) : !d ? null : rows.length === 0 ? (
            <EmptyState
              icon={<Zap size={28} />}
              title="No stocks in this list today"
              description={view === "horizon" ? "No setups meet the entry rules for this horizon. Cash is a valid position." : "Nothing classified under this action today."}
            />
          ) : (
            <SignalTable rows={rows} showSizing={view === "horizon" || group !== "avoid"} onAlert={setAlertSymbol} />
          )}
        </div>
      </Card>

      {/* Continuity */}
      {d && d.continuity.length > 0 && (
        <Card>
          <h3 className="text-sm font-bold mb-3" style={{ color: "var(--text-primary)" }}>Continuity vs previous report</h3>
          <div className="flex flex-wrap gap-2">
            {d.continuity.map((c: any) => (
              <span key={c.symbol + c.today_status} className={`badge ${c.today_status === "REMOVED" ? "badge-bearish" : c.today_status === "NEW" ? "badge-accent" : "badge-info"}`}>
                {c.symbol} · {humanize(c.today_status.toLowerCase())}
              </span>
            ))}
          </div>
        </Card>
      )}

      <div className="glass-card-static p-3 flex items-start gap-3" style={{ borderLeft: "3px solid var(--color-info)" }}>
        <Shield size={16} style={{ color: "var(--color-info)", flexShrink: 0, marginTop: 1 }} />
        <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>{d?._disclaimer || "Probabilistic estimates only. Protect capital first."}</p>
      </div>

      <AlertDialog open={!!alertSymbol} onClose={() => setAlertSymbol(null)} symbol={alertSymbol || ""} defaultType="signal_buy" />
    </div>
  );
}
