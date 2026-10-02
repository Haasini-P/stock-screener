"use client";

import { useEffect, useMemo } from "react";
import { marketAPI } from "@/lib/api";
import { useAppStore } from "@/lib/store";
import { useApi } from "@/lib/useApi";
import { fmtINR, fmtNum, fmtPct, toneColor } from "@/lib/format";
import { BucketChips, Card, EntryBadge, ErrorState, LoadingRows, PageHeader, RefreshButton, SectionHeader, Skeleton, StockLink } from "../ui";
import { SECTOR_ICONS } from "./DashboardView";

/** Background tint scaled by the size of the move (±3% = full intensity). */
function heat(v: number | null | undefined) {
  if (v == null) return "rgba(255,255,255,0.02)";
  const a = Math.min(Math.abs(v) / 3, 1) * 0.28 + 0.04;
  return v >= 0 ? `rgba(34,197,94,${a})` : `rgba(239,68,68,${a})`;
}

export default function SectorsView() {
  const { selectedSector, setSelectedSector, settings } = useAppStore();
  const sectors = useApi(() => marketAPI.sectors(), [], {
    refreshMs: settings.refreshSec ? Math.max(settings.refreshSec * 1000, 60000) : 0,
  });
  const list: any[] = useMemo(() => sectors.data?.sectors || [], [sectors.data]);

  useEffect(() => {
    if (!selectedSector && list.length) setSelectedSector(list[0].sector);
  }, [list, selectedSector, setSelectedSector]);

  const current = list.find((s) => s.sector === selectedSector);

  return (
    <div className="space-y-5">
      <PageHeader
        title="Sector Map"
        subtitle="Live heat map of the approved sector universe — select a sector to see its constituents"
        actions={<RefreshButton onClick={sectors.reload} busy={sectors.refreshing} updatedAt={sectors.updatedAt} />}
      />

      {sectors.error && <ErrorState message={sectors.error} onRetry={sectors.reload} />}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {sectors.loading
          ? Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-28 w-full" />)
          : list.map((s) => {
              const meta = SECTOR_ICONS[s.sector];
              const Icon = meta?.icon;
              const active = s.sector === selectedSector;
              return (
                <button
                  key={s.sector}
                  onClick={() => setSelectedSector(s.sector)}
                  className="rounded-xl p-4 text-left transition-all"
                  style={{
                    background: heat(s.change_pct),
                    border: `1px solid ${active ? "var(--border-accent)" : "var(--border-subtle)"}`,
                    boxShadow: active ? "var(--shadow-glow-indigo)" : undefined,
                  }}
                  aria-pressed={active}
                >
                  <div className="flex items-center gap-2 mb-2">
                    {Icon && <Icon size={14} style={{ color: meta.color }} />}
                    <span className="text-xs font-semibold" style={{ color: "var(--text-primary)" }}>{s.sector}</span>
                  </div>
                  <p className="text-xl font-bold tabular-nums" style={{ color: toneColor(s.change_pct) }}>{fmtPct(s.change_pct)}</p>
                  <p className="text-[11px] mt-1" style={{ color: "var(--text-secondary)" }}>
                    {s.advances}▲ {s.declines}▼ · 5D {fmtPct(s.return_5d)} · 20D {fmtPct(s.return_20d)}
                  </p>
                </button>
              );
            })}
      </div>

      {current && (
        <Card>
          <SectionHeader
            title={`${current.sector} — ${current.stocks} stocks`}
            subtitle={`Avg RSI ${fmtNum(current.avg_rsi, 1)} · ${current.bullish_signals} bullish setups · leader ${current.top_gainer ?? "—"} · laggard ${current.top_loser ?? "—"}`}
          />
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr><th>Stock</th><th>LTP</th><th>Day %</th><th>5D %</th><th>20D %</th><th>RSI</th><th>Vol ×</th><th>Trend</th><th>Signal</th><th>Setups</th></tr>
              </thead>
              <tbody>
                {current.constituents.map((r: any) => (
                  <tr key={r.symbol}>
                    <td><StockLink symbol={r.symbol} /><div className="text-[10px]" style={{ color: "var(--text-muted)" }}>{r.name}</div></td>
                    <td className="tabular-nums">{fmtINR(r.ltp)}</td>
                    <td className="tabular-nums" style={{ color: toneColor(r.change_pct) }}>{fmtPct(r.change_pct)}</td>
                    <td className="tabular-nums" style={{ color: toneColor(r.return_5d) }}>{fmtPct(r.return_5d)}</td>
                    <td className="tabular-nums" style={{ color: toneColor(r.return_20d) }}>{fmtPct(r.return_20d)}</td>
                    <td className="tabular-nums">{fmtNum(r.rsi, 1)}</td>
                    <td className="tabular-nums">{fmtNum(r.volume_ratio)}</td>
                    <td className="text-xs whitespace-nowrap">{r.trend}</td>
                    <td><EntryBadge entry={r.entry} /></td>
                    <td><BucketChips buckets={r.buckets} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      {sectors.loading && <LoadingRows rows={6} />}
    </div>
  );
}
