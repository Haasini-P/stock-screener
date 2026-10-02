"use client";

/**
 * Renders AI-generated markdown (headers, tables, bold, lists) using this
 * app's own dark-theme tokens — the research-report prompt produces real
 * markdown structure (tables for scores, headers per section), so showing it
 * as a single plain-text blob loses most of its readability.
 */

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function MarkdownContent({ content }: { content: string }) {
  return (
    <div className="text-xs space-y-2" style={{ color: "var(--text-secondary)" }}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => <h3 className="text-sm font-bold mt-3 mb-1" style={{ color: "var(--text-primary)" }}>{children}</h3>,
          h2: ({ children }) => <h4 className="text-xs font-bold mt-3 mb-1" style={{ color: "var(--text-primary)" }}>{children}</h4>,
          h3: ({ children }) => <h5 className="text-xs font-semibold mt-2 mb-1" style={{ color: "var(--text-primary)" }}>{children}</h5>,
          p: ({ children }) => <p className="leading-relaxed">{children}</p>,
          strong: ({ children }) => <strong style={{ color: "var(--text-primary)" }}>{children}</strong>,
          ul: ({ children }) => <ul className="list-disc pl-4 space-y-0.5">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal pl-4 space-y-0.5">{children}</ol>,
          blockquote: ({ children }) => (
            <blockquote className="pl-3 py-1 my-2" style={{ borderLeft: "3px solid var(--accent-indigo)", color: "var(--text-primary)" }}>
              {children}
            </blockquote>
          ),
          hr: () => <hr style={{ borderColor: "var(--border-subtle)" }} className="my-3" />,
          table: ({ children }) => (
            <div className="table-scroll my-2">
              <table className="data-table">{children}</table>
            </div>
          ),
          code: ({ children }) => (
            <code className="font-mono text-[11px] px-1 rounded" style={{ background: "rgba(255,255,255,0.06)" }}>{children}</code>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
