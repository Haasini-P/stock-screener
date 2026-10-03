"use client";

import { useEffect } from "react";

export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="min-h-screen flex items-center justify-center px-4" style={{ background: "var(--bg-primary)" }}>
      <div className="glass-card-static p-6 max-w-md w-full text-center space-y-3">
        <h2 className="text-lg font-bold" style={{ color: "var(--text-primary)" }}>Something went wrong</h2>
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
          This page hit an unexpected error. Your data is safe — try again, or reload if it keeps happening.
        </p>
        <div className="flex gap-2 justify-center">
          <button className="btn-primary text-xs" onClick={reset}>Try again</button>
          <button className="btn-secondary text-xs" onClick={() => window.location.reload()}>Reload page</button>
        </div>
      </div>
    </div>
  );
}
