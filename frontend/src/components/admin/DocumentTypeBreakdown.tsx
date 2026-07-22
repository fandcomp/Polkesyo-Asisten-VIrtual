"use client"

import { useMemo, useState } from "react"
import type { AdminDocument } from "@/types/admin"
import { DocumentList } from "./DocumentList"

interface DocumentTypeBreakdownProps {
  documents: AdminDocument[]
  selectedId: string | null
  onSelect: (id: string) => void
}

export function DocumentTypeBreakdown({ documents, selectedId, onSelect }: DocumentTypeBreakdownProps) {
  const [activeType, setActiveType] = useState<string | null>(null)

  const countsByType = useMemo(() => {
    const counts = new Map<string, number>()
    for (const doc of documents) {
      counts.set(doc.documentType, (counts.get(doc.documentType) ?? 0) + 1)
    }
    return counts
  }, [documents])

  const types = Array.from(countsByType.keys()).sort()

  const filteredDocuments = activeType ? documents.filter((d) => d.documentType === activeType) : documents

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => setActiveType(null)}
          className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors duration-300 ${
            activeType === null
              ? "border-primary bg-surface-elevated text-primary"
              : "border-hairline bg-surface text-ink-muted hover:bg-surface-elevated"
          }`}
        >
          Semua Jenis ({documents.length})
        </button>
        {types.map((type) => (
          <button
            key={type}
            type="button"
            onClick={() => setActiveType(type)}
            className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors duration-300 ${
              activeType === type
                ? "border-primary bg-surface-elevated text-primary"
                : "border-hairline bg-surface text-ink-muted hover:bg-surface-elevated"
            }`}
          >
            {type} ({countsByType.get(type)})
          </button>
        ))}
      </div>

      {filteredDocuments.length === 0 ? (
        <p className="rounded-2xl border border-hairline bg-surface-elevated p-6 text-center text-sm text-ink-muted">
          Tidak ada dokumen untuk jenis ini.
        </p>
      ) : (
        <DocumentList documents={filteredDocuments} selectedId={selectedId} onSelect={onSelect} />
      )}
    </div>
  )
}
