"use client";

/**
 * StockMind AI — Data fetching hook with loading/error state, manual reload
 * and optional auto-refresh (paused while the browser tab is hidden).
 */

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { errorMessage } from "./api";

interface Options {
  /** Auto-refresh interval in ms (0/undefined = off). */
  refreshMs?: number;
  /** Skip fetching until true (e.g. waiting for auth). */
  enabled?: boolean;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any -- API payloads are untyped JSON
export function useApi<T = any>(
  fetcher: () => Promise<{ data: T }>,
  deps: unknown[] = [],
  { refreshMs, enabled = true }: Options = {}
) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const requestId = useRef(0);
  const fetcherRef = useRef(fetcher);

  useLayoutEffect(() => {
    fetcherRef.current = fetcher;
  });

  const run = useCallback(async (background = false) => {
    const id = ++requestId.current;
    if (background) setRefreshing(true);
    else setPending(true);
    try {
      const res = await fetcherRef.current();
      if (id !== requestId.current) return;
      setData(res.data);
      setError("");
      setUpdatedAt(new Date());
    } catch (err) {
      if (id !== requestId.current) return;
      setError(errorMessage(err));
    } finally {
      if (id === requestId.current) {
        setPending(false);
        setRefreshing(false);
      }
    }
  }, []);

  useEffect(() => {
    // Fetching on mount/dependency change is this hook's purpose; run() marks the request pending.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (enabled) run(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, ...deps]);

  useEffect(() => {
    if (!enabled || !refreshMs) return;
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") run(true);
    }, refreshMs);
    return () => clearInterval(timer);
  }, [enabled, refreshMs, run]);

  return {
    data,
    error,
    loading: enabled && pending,
    refreshing,
    updatedAt,
    reload: () => run(true),
    setData,
  };
}
