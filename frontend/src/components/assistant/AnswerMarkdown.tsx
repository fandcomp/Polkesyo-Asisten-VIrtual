"use client"

import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

// Links/URLs are rendered as plain text, not clickable anchors, per the assistant's
// no-links output policy (CLAUDE.md §26.1/§34) -- the LLM should not be steering users
// to arbitrary URLs, even ones it copied verbatim out of a source document.
export function AnswerMarkdown({ content }: { content: string }) {
  return (
    <div className="prose-chat text-sm leading-relaxed">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ children }) => <span>{children}</span>,
          p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
          strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
          h1: ({ children }) => <p className="mb-2 text-base font-bold last:mb-0">{children}</p>,
          h2: ({ children }) => <p className="mb-2 text-base font-bold last:mb-0">{children}</p>,
          h3: ({ children }) => <p className="mb-2 text-sm font-bold last:mb-0">{children}</p>,
          h4: ({ children }) => <p className="mb-2 text-sm font-semibold last:mb-0">{children}</p>,
          ul: ({ children }) => <ul className="mb-2 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>,
          ol: ({ children }) => <ol className="mb-2 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>,
          li: ({ children }) => <li className="leading-relaxed">{children}</li>,
          table: ({ children }) => (
            <div className="mb-2 overflow-x-auto last:mb-0">
              <table className="w-full min-w-[280px] border-collapse text-xs">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-surface">{children}</thead>,
          th: ({ children }) => (
            <th className="border border-hairline px-2 py-1 text-left font-semibold">{children}</th>
          ),
          td: ({ children }) => <td className="border border-hairline px-2 py-1 align-top">{children}</td>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
