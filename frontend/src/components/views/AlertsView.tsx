"use client";

import { useState } from "react";
import Link from "next/link";
import { Bell, BellPlus, CheckCircle2, Pause, Play, RefreshCw, Trash2 } from "lucide-react";
import { alertsAPI, errorMessage } from "@/lib/api";
import { useAppStore } from "@/lib/store";
import { useApi } from "@/lib/useApi";
import { fmtDate, humanize, timeAgo } from "@/lib/format";
import AlertDialog, { ALERT_TYPES } from "../AlertDialog";
import { Card, EmptyState, ErrorState, LoadingRows, PageHeader, StockLink } from "../ui";

function describe(a: any) {
  const t = ALERT_TYPES.find((x) => x.value === a.alert_type);
  if (!t) return a.alert_type;
  if (a.alert_type === "signal_buy") return t.label;
  return t.unit === "₹" ? `${t.label} ₹${Number(a.value).toLocaleString("en-IN")}` : `${t.label} ${a.value}%`;
}

export default function AlertsView() {
  const { isAuthenticated, hydrated, toast } = useAppStore();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const [filter, setFilter] = useState<"all" | "active" | "triggered" | "paused">("all");

  // Evaluate against live prices first so statuses match the notification bell
  const alerts = useApi(
    () => alertsAPI.check().catch(() => null).then(() => alertsAPI.list()),
    [],
    { enabled: hydrated && isAuthenticated, refreshMs: 60_000 }
  );

  if (hydrated && !isAuthenticated) {
    return (
      <div>
        <PageHeader title="Alerts" subtitle="Price, day-change and BUY-signal alerts evaluated against live Upstox data" />
        <EmptyState
          icon={<Bell size={28} />}
          title="Sign in to use alerts"
          description="Alerts are stored in your account and checked every minute while the app is open. You'll get an in-app notification and, optionally, a browser notification."
          action={
            <div className="flex gap-2">
              <Link href="/login?next=%2F%23alerts" className="btn-primary text-xs">Sign in</Link>
              <Link href="/login?mode=register&next=%2F%23alerts" className="btn-secondary text-xs">Create account</Link>
            </div>
          }
        />
      </div>
    );
  }

  const list: any[] = alerts.data?.alerts || [];
  const shown = list.filter((a) =>
    filter === "all" ? true : filter === "active" ? a.is_active && !a.is_triggered : filter === "triggered" ? a.is_triggered : !a.is_active
  );

  const act = async (id: string, fn: () => Promise<unknown>, success: string) => {
    setBusyId(id);
    try {
      await fn();
      toast(success, "success");
      alerts.reload();
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setBusyId(null);
    }
  };

  const checkNow = async () => {
    setChecking(true);
    try {
      const res = await alertsAPI.check();
      const n = res.data.newly_triggered.length;
      toast(n ? `${n} alert${n > 1 ? "s" : ""} triggered` : `Checked ${res.data.checked} alerts — none triggered`, n ? "success" : "info");
      alerts.reload();
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setChecking(false);
    }
  };

  return (
    <div className="space-y-5">
      <PageHeader
        title="Alerts"
        subtitle="Checked against live quotes and computed signals every minute while the app is open"
        actions={
          <>
            <button className="btn-secondary text-xs" style={{ padding: "6px 12px" }} onClick={checkNow} disabled={checking || !list.length}>
              <RefreshCw size={13} className={checking ? "animate-spin" : ""} /> Check now
            </button>
            <button className="btn-primary text-xs" style={{ padding: "6px 14px" }} onClick={() => setDialogOpen(true)}>
              <BellPlus size={14} /> New alert
            </button>
          </>
        }
      />

      <div className="flex gap-2">
        {(["all", "active", "triggered", "paused"] as const).map((f) => (
          <button key={f} className={`chip ${filter === f ? "chip-active" : ""}`} onClick={() => setFilter(f)}>
            {f[0].toUpperCase() + f.slice(1)}
          </button>
        ))}
      </div>

      <Card padded={false}>
        <div className="p-3">
          {alerts.loading ? (
            <div className="p-2"><LoadingRows rows={4} /></div>
          ) : alerts.error ? (
            <ErrorState message={alerts.error} onRetry={alerts.reload} />
          ) : shown.length === 0 ? (
            <EmptyState
              icon={<Bell size={28} />}
              title={list.length ? "No alerts in this filter" : "No alerts yet"}
              description="Create an alert to be notified when a stock crosses a price or moves by a percentage."
              action={<button className="btn-primary text-xs" onClick={() => setDialogOpen(true)}><BellPlus size={14} /> New alert</button>}
            />
          ) : (
            <div className="table-scroll">
              <table className="data-table">
                <thead><tr><th>Stock</th><th>Condition</th><th>Status</th><th>Note</th><th>Created</th><th className="text-right">Actions</th></tr></thead>
                <tbody>
                  {shown.map((a) => (
                    <tr key={a.id}>
                      <td><StockLink symbol={a.symbol} /></td>
                      <td className="text-xs">{describe(a)}</td>
                      <td>
                        {a.is_triggered ? (
                          <span className="badge badge-bullish" title={fmtDate(a.triggered_at)}>
                            <CheckCircle2 size={10} /> {a.entry_type ? humanize(a.entry_type) : "Triggered"} {timeAgo(a.triggered_at)}
                            {a.triggered_price ? ` @ ₹${a.triggered_price}` : ""}
                            {a.entry_zone ? ` · entry ₹${a.entry_zone[0]}–₹${a.entry_zone[1]}` : ""}
                            {a.stop_loss ? ` · SL ₹${a.stop_loss}` : ""}
                          </span>
                        ) : a.is_active ? (
                          <span className="badge badge-info">Watching</span>
                        ) : (
                          <span className="badge badge-neutral">Paused</span>
                        )}
                      </td>
                      <td className="text-xs max-w-48 truncate" title={a.message || ""}>{a.message || "—"}</td>
                      <td className="text-xs">{fmtDate(a.created_at)}</td>
                      <td>
                        <div className="flex justify-end gap-1">
                          {a.is_triggered || !a.is_active ? (
                            <button className="btn-ghost text-xs" disabled={busyId === a.id} onClick={() => act(a.id, () => alertsAPI.update(a.id, { is_active: true }), `${a.symbol} alert re-armed`)} title="Re-arm">
                              <Play size={13} /> Re-arm
                            </button>
                          ) : (
                            <button className="btn-ghost text-xs" disabled={busyId === a.id} onClick={() => act(a.id, () => alertsAPI.update(a.id, { is_active: false }), `${a.symbol} alert paused`)} title="Pause">
                              <Pause size={13} /> Pause
                            </button>
                          )}
                          <button
                            className="btn-ghost text-xs"
                            style={{ color: "var(--color-bearish)" }}
                            disabled={busyId === a.id}
                            onClick={() => act(a.id, () => alertsAPI.remove(a.id), `${a.symbol} alert deleted`)}
                            title="Delete"
                            aria-label={`Delete ${a.symbol} alert`}
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Card>

      <AlertDialog open={dialogOpen} onClose={() => setDialogOpen(false)} onCreated={alerts.reload} />
    </div>
  );
}
