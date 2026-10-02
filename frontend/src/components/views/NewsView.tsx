"use client";

import { useMemo, useState } from "react";
import { ExternalLink, Newspaper } from "lucide-react";
import { marketAPI } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { fmtDate, timeAgo } from "@/lib/format";
import { Card, EmptyState, ErrorState, LoadingRows, PageHeader, RefreshButton } from "../ui";
import { SECTOR_ICONS } from "./DashboardView";
import Link from "next/link";

export default function NewsView() {
  const [sector, setSector] = useState("");
  const [query, setQuery] = useState("");
  const news = useApi(() => marketAPI.news(sector || undefined), [sector], { refreshMs: 5 * 60_000 });

  const items: any[] = useMemo(() => {
    const all = news.data?.news || [];
    const q = query.trim().toLowerCase();
    if (!q) return all;
    return all.filter(
      (n: any) =>
        n.heading?.toLowerCase().includes(q) ||
        n.summary?.toLowerCase().includes(q) ||
        n.symbols?.some((s: string) => s.toLowerCase().includes(q))
    );
  }, [news.data, query]);

  return (
    <div className="space-y-5">
      <PageHeader
        title="News & Events"
        subtitle="Headlines for the approved universe from Upstox. Every item links to its original source — nothing is generated."
        actions={<RefreshButton onClick={news.reload} busy={news.refreshing} updatedAt={news.updatedAt} />}
      />

      <Card>
        <div className="flex flex-col lg:flex-row gap-3 lg:items-center">
          <input className="input lg:max-w-xs" placeholder="Filter headlines or symbols…" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Filter news" />
          <div className="flex gap-2 overflow-x-auto pb-1">
            <button className={`chip ${sector === "" ? "chip-active" : ""}`} onClick={() => setSector("")}>All sectors</button>
            {Object.keys(SECTOR_ICONS).map((s) => (
              <button key={s} className={`chip ${sector === s ? "chip-active" : ""}`} onClick={() => setSector(s)}>{s}</button>
            ))}
          </div>
        </div>
      </Card>

      {news.loading ? (
        <Card><LoadingRows rows={6} /></Card>
      ) : news.error ? (
        <ErrorState message={news.error} onRetry={news.reload} />
      ) : items.length === 0 ? (
        <EmptyState icon={<Newspaper size={28} />} title="No news found" description={query ? "No headlines match your filter." : "Upstox returned no recent articles for this selection."} />
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          {items.map((n) => (
            <article key={n.url || n.heading} className="glass-card p-4 flex gap-4">
              {n.thumbnail && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={n.thumbnail} alt="" className="w-24 h-20 object-cover rounded-lg shrink-0 hidden sm:block" loading="lazy" />
              )}
              <div className="min-w-0 flex-1">
                <a
                  href={n.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm font-semibold hover:underline inline-flex items-start gap-1"
                  style={{ color: "var(--text-primary)" }}
                >
                  {n.heading} <ExternalLink size={12} className="shrink-0 mt-1" style={{ color: "var(--text-muted)" }} />
                </a>
                {n.summary && <p className="text-xs mt-1 line-clamp-2" style={{ color: "var(--text-secondary)" }}>{n.summary}</p>}
                <div className="flex flex-wrap items-center gap-2 mt-2">
                  <span className="text-[10px]" style={{ color: "var(--text-muted)" }} title={fmtDate(n.published_at)}>
                    {n.source} · {timeAgo(n.published_at)}
                  </span>
                  {n.symbols?.map((s: string) => (
                    <Link key={s} href={`/stock/${s}`} className="badge badge-accent" style={{ fontSize: 9 }}>{s}</Link>
                  ))}
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
