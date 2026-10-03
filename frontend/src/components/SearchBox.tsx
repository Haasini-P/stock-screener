"use client";

/**
 * Stock search with live Upstox instrument suggestions and keyboard navigation.
 */

import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { Search } from "lucide-react";
import { marketAPI, searchUSUniverse } from "@/lib/api";

export interface Suggestion {
  symbol: string;
  name: string;
  short_name?: string;
  isin?: string;
}

interface Props {
  onSelect: (symbol: string) => void;
  placeholder?: string;
  shortcutHint?: boolean;
  autoFocus?: boolean;
  className?: string;
  /** "US" searches StockMind's small approved US ticker list (client-side,
   * no Upstox/NSE call) instead of the default Upstox/NSE instrument search. */
  market?: "IN" | "US";
}

export interface SearchBoxHandle {
  focus: () => void;
}

const SearchBox = forwardRef<SearchBoxHandle, Props>(function SearchBox(
  { onSelect, placeholder = "Search NSE stocks…", shortcutHint = false, autoFocus = false, className = "", market = "IN" },
  ref
) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Suggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  useImperativeHandle(ref, () => ({ focus: () => inputRef.current?.focus() }));

  // Debounced instrument search
  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) {
      setResults([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    const timer = setTimeout(() => {
      const search = market === "US" ? searchUSUniverse(q) : marketAPI.searchInstruments(q).then((res) => res.data?.results || []);
      search
        .then((results) => !cancelled && setResults(results))
        .catch(() => !cancelled && setResults([]))
        .finally(() => !cancelled && setLoading(false));
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query, market]);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (!wrapperRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const choose = (symbol: string) => {
    const s = symbol.trim().toUpperCase();
    if (!s) return;
    onSelect(s);
    setQuery("");
    setResults([]);
    setOpen(false);
    inputRef.current?.blur();
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActive((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, -1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      choose(active >= 0 && results[active] ? results[active].symbol : query);
    } else if (e.key === "Escape") {
      setOpen(false);
      inputRef.current?.blur();
    }
  };

  return (
    <div ref={wrapperRef} className={`relative ${className}`}>
      <div
        className="flex items-center gap-2 px-3 py-2 rounded-lg"
        style={{ background: "var(--bg-card)", border: "1px solid var(--border-subtle)" }}
      >
        <Search size={15} style={{ color: "var(--text-muted)", flexShrink: 0 }} />
        <input
          ref={inputRef}
          type="text"
          value={query}
          autoFocus={autoFocus}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
            setActive(-1);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          className="bg-transparent border-none outline-none text-sm w-full"
          style={{ color: "var(--text-primary)" }}
          aria-label="Search stocks"
          aria-autocomplete="list"
          aria-controls="stock-search-listbox"
          aria-expanded={open && results.length > 0}
          role="combobox"
        />
        {shortcutHint && (
          <kbd
            className="hidden sm:inline text-[10px] px-1.5 py-0.5 rounded font-mono"
            style={{ background: "rgba(255,255,255,0.05)", color: "var(--text-muted)", border: "1px solid var(--border-subtle)" }}
          >
            Ctrl K
          </kbd>
        )}
      </div>

      {open && query.trim().length >= 2 && (
        <div id="stock-search-listbox" className="popover left-0 right-0 mt-1" role="listbox">
          {loading && results.length === 0 ? (
            <div className="px-4 py-3 text-xs" style={{ color: "var(--text-muted)" }}>Searching…</div>
          ) : results.length === 0 ? (
            <button className="popover-item" onClick={() => choose(query)}>
              Open <strong className="font-mono">{query.trim().toUpperCase()}</strong>
            </button>
          ) : (
            results.map((r, i) => (
              <button
                key={r.isin || r.symbol}
                className="popover-item"
                data-active={i === active}
                onMouseEnter={() => setActive(i)}
                onClick={() => choose(r.symbol)}
                role="option"
                aria-selected={i === active}
              >
                <span className="font-semibold font-mono w-24 shrink-0" style={{ color: "var(--text-primary)" }}>{r.symbol}</span>
                <span className="truncate text-xs">{r.short_name || r.name}</span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
});

export default SearchBox;
