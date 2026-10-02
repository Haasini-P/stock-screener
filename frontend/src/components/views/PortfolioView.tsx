"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Crosshair, Link2, Link2Off, PieChart as PieIcon, PlusCircle, ShieldAlert, TrendingDown, Wallet, X } from "lucide-react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { authAPI, errorMessage, healthAPI, ordersAPI, portfolioAPI, PortfolioRecommendation } from "@/lib/api";
import { useAppStore } from "@/lib/store";
import { useApi } from "@/lib/useApi";
import { fmtINR, fmtNum, fmtPct, humanize, timeAgo, toneColor } from "@/lib/format";
import { useNavigateTab } from "../AppShell";
import OrderTicketDialog, { OrderDefaults } from "../OrderTicketDialog";
import { Card, EmptyState, ErrorState, KeyValue, LoadingRows, PageHeader, RefreshButton, SectionHeader, StockLink } from "../ui";

const ACTION_BADGE: Record<string, string> = { ADD: "badge-bullish", HOLD: "badge-neutral", REDUCE: "badge-bearish" };

const PIE_COLORS = ["#6366f1", "#22d3ee", "#22c55e", "#f59e0b", "#ef4444", "#a855f7", "#ec4899", "#14b8a6", "#8b92a5"];

function ActiveBracketsCard() {
  const { toast } = useAppStore();
  const brackets = useApi(() => ordersAPI.listBrackets(), []);
  const active = (brackets.data || []).filter((b) => b.status === "ACTIVE");

  const cancel = async (id: string, symbol: string) => {
    if (!window.confirm(`Cancel the target/stop-loss bracket for ${symbol}?`)) return;
    try {
      await ordersAPI.cancelBracket(id);
      toast(`Bracket cancelled for ${symbol}`, "success");
      brackets.reload();
    } catch (err) {
      toast(errorMessage(err, "Could not cancel this bracket."), "error");
    }
  };

  return (
    <Card>
      <SectionHeader icon={<Crosshair size={16} />} title="Active Brackets" subtitle="Target/stop-loss orders placed from Scanner or Stock Report" />
      {brackets.loading ? (
        <LoadingRows rows={2} />
      ) : brackets.error ? (
        <ErrorState message={brackets.error} onRetry={brackets.reload} />
      ) : active.length === 0 ? (
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>No active brackets. Add one from a Buy/Sell order ticket.</p>
      ) : (
        <div className="space-y-2">
          {active.map((b) => (
            <div key={b.id} className="flex items-center justify-between gap-3 p-2.5 rounded-lg text-xs" style={{ background: "rgba(255,255,255,0.02)", border: "1px solid var(--border-subtle)" }}>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <StockLink symbol={b.symbol} />
                  <span className="badge badge-neutral">{b.provider}</span>
                  {b.trailing_amount != null && <span className="badge badge-accent">Trailing ₹{fmtNum(b.trailing_amount)}</span>}
                </div>
                <p style={{ color: "var(--text-muted)" }}>
                  Target {fmtINR(b.target_price)} · Stop {fmtINR(b.stop_price)}
                  {b.last_trailed_at ? ` · last trailed ${timeAgo(b.last_trailed_at)}` : ""}
                  {b.last_error ? ` · ⚠ ${b.last_error}` : ""}
                </p>
              </div>
              <button className="btn-ghost text-xs shrink-0" onClick={() => cancel(b.id, b.symbol)} title="Cancel bracket">
                <X size={13} />
              </button>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function RiskSettingsCard() {
  const { settings } = useAppStore();
  const navigate = useNavigateTab();
  return (
    <Card>
      <SectionHeader
        icon={<ShieldAlert size={16} />}
        title="Risk framework"
        actions={<button className="btn-ghost text-xs" onClick={() => navigate("settings")}>Edit</button>}
      />
      <div className="grid grid-cols-3 gap-4">
        <KeyValue label="Capital" value={fmtINR(settings.capital, 0)} />
        <KeyValue label="Risk / trade" value={`${settings.riskPct}%`} />
        <KeyValue label="Max loss / trade" value={fmtINR((settings.capital * settings.riskPct) / 100, 0)} valueColor="var(--color-bearish)" />
      </div>
      <p className="text-[11px] mt-3" style={{ color: "var(--text-muted)" }}>
        Position sizes across Daily Signals and stock analysis use these values.
      </p>
    </Card>
  );
}

export default function PortfolioView() {
  const { isAuthenticated, hydrated, toast } = useAppStore();
  const navigate = useNavigateTab();
  const [busy, setBusy] = useState(false);
  const [order, setOrder] = useState<{ symbol: string; side: "BUY" | "SELL"; defaults: OrderDefaults } | null>(null);

  const system = useApi(() => healthAPI.system(), [isAuthenticated], { enabled: hydrated });
  const connected = !!system.data?.user_upstox_connected;
  const portfolio = useApi(() => portfolioAPI.overview(), [connected], { enabled: hydrated && isAuthenticated && connected });
  const funds = useApi(() => portfolioAPI.funds(), [connected], { enabled: hydrated && isAuthenticated && connected });
  // Separate, slower fetch — runs full signal analysis per holding (several Upstox calls
  // each), so it's kept independent of the fast overview/funds calls above.
  const recommendations = useApi(() => portfolioAPI.recommendations(), [connected], { enabled: hydrated && isAuthenticated && connected });
  const recBySymbol = useMemo(() => {
    const m = new Map<string, PortfolioRecommendation>();
    for (const r of recommendations.data?.items || []) m.set(r.symbol, r);
    return m;
  }, [recommendations.data]);

  const connect = async () => {
    setBusy(true);
    try {
      const res = await authAPI.upstoxConnect();
      window.location.href = res.data.authorization_url;
    } catch (err) {
      toast(errorMessage(err), "error");
      setBusy(false);
    }
  };

  const disconnect = async () => {
    setBusy(true);
    try {
      await authAPI.upstoxDisconnect();
      toast("Upstox account disconnected", "success");
      system.reload();
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setBusy(false);
    }
  };

  if (hydrated && !isAuthenticated) {
    return (
      <div className="space-y-5">
        <PageHeader title="Portfolio" subtitle="Holdings, positions and P&L from your Upstox account" />
        <EmptyState
          icon={<Wallet size={28} />}
          title="Sign in to view your portfolio"
          description="Your holdings come from your own Upstox account via secure OAuth. We never see your Upstox password, and tokens are encrypted at rest."
          action={
            <div className="flex gap-2">
              <Link href="/login?next=%2F%23portfolio" className="btn-primary text-xs">Sign in</Link>
              <Link href="/login?mode=register&next=%2F%23portfolio" className="btn-secondary text-xs">Create account</Link>
            </div>
          }
        />
        <RiskSettingsCard />
      </div>
    );
  }

  if (system.loading) return <Card><LoadingRows rows={5} /></Card>;

  if (!connected) {
    const oauthReady = system.data?.oauth_configured;
    return (
      <div className="space-y-5">
        <PageHeader title="Portfolio" subtitle="Holdings, positions and P&L from your Upstox account" />
        {system.error && <ErrorState message={system.error} onRetry={system.reload} />}
        <EmptyState
          icon={<Link2 size={28} />}
          title="Connect your Upstox account"
          description={
            oauthReady
              ? "You'll be redirected to Upstox to approve read access. Market data already works through the analytics token; this adds your personal holdings and funds."
              : "The server has no Upstox app credentials yet. Add them in Settings → Broker API Credentials."
          }
          action={
            oauthReady ? (
              <button className="btn-primary text-xs" onClick={connect} disabled={busy}>
                <Link2 size={14} /> {busy ? "Redirecting…" : "Connect Upstox"}
              </button>
            ) : (
              <button className="btn-primary text-xs" onClick={() => navigate("settings")}>
                <Link2 size={14} /> Go to Broker API Credentials
              </button>
            )
          }
        />
        <ActiveBracketsCard />
        <RiskSettingsCard />
      </div>
    );
  }

  const p = portfolio.data;
  const summary = p?.summary;
  const holdings: any[] = p?.holdings || [];
  const allocation = holdings
    .filter((h) => h.current_value > 0)
    .sort((a, b) => b.current_value - a.current_value)
    .map((h) => ({ name: h.symbol, value: h.current_value }));
  const equity = funds.data?.data?.equity;

  return (
    <div className="space-y-5">
      <PageHeader
        title="Portfolio"
        subtitle="Live from your connected Upstox account"
        actions={
          <>
            <RefreshButton onClick={() => { portfolio.reload(); funds.reload(); }} busy={portfolio.refreshing} updatedAt={portfolio.updatedAt} />
            <button className="btn-secondary text-xs" style={{ padding: "6px 12px" }} onClick={disconnect} disabled={busy}>
              <Link2Off size={13} /> Disconnect
            </button>
          </>
        }
      />

      {portfolio.error && <ErrorState message={portfolio.error} onRetry={portfolio.reload} />}

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <Card><KeyValue label="Invested" value={fmtINR(summary?.total_invested, 0)} /></Card>
        <Card><KeyValue label="Current value" value={fmtINR(summary?.total_current_value, 0)} /></Card>
        <Card>
          <KeyValue label="Total P&L" value={`${fmtINR(summary?.total_pnl, 0)} (${fmtPct(summary?.total_pnl_percentage)})`} valueColor={toneColor(summary?.total_pnl)} />
        </Card>
        <Card><KeyValue label="Concentration" value={p ? `${p.risk.concentration_level} (top ${fmtNum(p.risk.top_holding_pct, 1)}%)` : "—"} /></Card>
        <Card><KeyValue label="Available margin" value={fmtINR(equity?.available_margin, 0)} /></Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <Card className="lg:col-span-2" padded={false}>
          <div className="px-5 pt-4">
            <SectionHeader
              title={`Holdings (${holdings.length})`}
              subtitle={recommendations.loading ? "Analyzing each holding for add/hold/reduce…" : undefined}
            />
          </div>
          <div className="px-3 pb-3">
            {portfolio.loading ? (
              <LoadingRows rows={5} />
            ) : holdings.length === 0 ? (
              <EmptyState title="No long-term holdings" description="Your Upstox account has no delivery holdings." />
            ) : (
              <div className="table-scroll">
                <table className="data-table">
                  <thead><tr><th>Stock</th><th>Qty</th><th>Avg</th><th>LTP</th><th>Value</th><th>P&L</th><th>Day %</th><th>Alloc</th><th>Add or remove?</th></tr></thead>
                  <tbody>
                    {holdings.map((h) => {
                      const rec = recBySymbol.get(h.symbol);
                      return (
                      <tr key={h.instrument_key}>
                        <td><StockLink symbol={h.symbol} /></td>
                        <td className="tabular-nums">{h.quantity}</td>
                        <td className="tabular-nums">{fmtINR(h.average_price)}</td>
                        <td className="tabular-nums">{fmtINR(h.last_price)}</td>
                        <td className="tabular-nums">{fmtINR(h.current_value, 0)}</td>
                        <td className="tabular-nums" style={{ color: toneColor(h.pnl) }}>{fmtINR(h.pnl, 0)} ({fmtPct(h.pnl_percentage)})</td>
                        <td className="tabular-nums" style={{ color: toneColor(h.day_change_percentage) }}>{fmtPct(h.day_change_percentage)}</td>
                        <td className="tabular-nums">{fmtNum(h.allocation_pct, 1)}%</td>
                        <td>
                          {recommendations.loading && !rec ? (
                            <span className="text-xs" style={{ color: "var(--text-muted)" }}>…</span>
                          ) : rec?.error ? (
                            <span className="text-[10px]" style={{ color: "var(--text-muted)" }} title={rec.error}>Unavailable</span>
                          ) : rec?.action ? (
                            <div className="flex items-center gap-1.5">
                              <span
                                className={`badge ${ACTION_BADGE[rec.action]}`}
                                title={rec.explanation || humanize(rec.entry || "")}
                              >
                                {rec.action}
                              </span>
                              {rec.action === "ADD" && (
                                <button
                                  className="btn-ghost text-xs"
                                  style={{ padding: "2px 6px" }}
                                  title={`Buy more ${h.symbol} — entry ${rec.entry_zone ? `₹${rec.entry_zone[0]}–₹${rec.entry_zone[1]}` : "—"}, stop ₹${rec.stop_loss ?? "—"}`}
                                  onClick={() =>
                                    setOrder({
                                      symbol: h.symbol,
                                      side: "BUY",
                                      defaults: {
                                        quantity: 1,
                                        price: rec.entry_zone?.[1] ?? h.last_price,
                                        product: "DELIVERY",
                                        target: rec.target_1,
                                        stopLoss: rec.stop_loss,
                                      },
                                    })
                                  }
                                >
                                  <PlusCircle size={13} />
                                </button>
                              )}
                              {rec.action === "REDUCE" && (
                                <button
                                  className="btn-ghost text-xs"
                                  style={{ padding: "2px 6px", color: "var(--color-bearish)" }}
                                  title={`Trim/exit ${h.symbol}`}
                                  onClick={() =>
                                    setOrder({
                                      symbol: h.symbol,
                                      side: "SELL",
                                      defaults: { quantity: h.quantity, price: h.last_price, product: "DELIVERY" },
                                    })
                                  }
                                >
                                  <TrendingDown size={13} />
                                </button>
                              )}
                            </div>
                          ) : (
                            <span className="text-xs" style={{ color: "var(--text-muted)" }}>—</span>
                          )}
                        </td>
                      </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </Card>

        <div className="space-y-5">
          <Card>
            <SectionHeader icon={<PieIcon size={16} />} title="Allocation" />
            {allocation.length === 0 ? (
              <p className="text-xs" style={{ color: "var(--text-muted)" }}>No holdings to chart.</p>
            ) : (
              <div className="h-52">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={allocation} dataKey="value" nameKey="name" innerRadius={45} outerRadius={80} paddingAngle={2} isAnimationActive={false}>
                      {allocation.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                    </Pie>
                    <Tooltip
                      contentStyle={{ background: "#111318", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, fontSize: 12 }}
                      formatter={(v: any) => fmtINR(Number(v), 0)}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            )}
          </Card>
          <ActiveBracketsCard />
          <RiskSettingsCard />
        </div>
      </div>

      <Card>
        <SectionHeader title={`Open positions (${p?.positions?.length ?? 0})`} />
        {!p?.positions?.length ? (
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>No open intraday or short-term positions.</p>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead><tr><th>Symbol</th><th>Product</th><th>Qty</th><th>Avg</th><th>LTP</th><th>P&L</th></tr></thead>
              <tbody>
                {p.positions.map((pos: any, i: number) => (
                  <tr key={i}>
                    <td><StockLink symbol={pos.trading_symbol || pos.tradingsymbol} /></td>
                    <td className="text-xs">{pos.product}</td>
                    <td className="tabular-nums">{pos.quantity}</td>
                    <td className="tabular-nums">{fmtINR(pos.average_price)}</td>
                    <td className="tabular-nums">{fmtINR(pos.last_price)}</td>
                    <td className="tabular-nums" style={{ color: toneColor(pos.pnl) }}>{fmtINR(pos.pnl)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {order && (
        <OrderTicketDialog
          open={!!order}
          onClose={() => setOrder(null)}
          symbol={order.symbol}
          side={order.side}
          defaults={order.defaults}
        />
      )}
    </div>
  );
}
