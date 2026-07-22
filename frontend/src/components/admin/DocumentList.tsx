"use client"

import { useMemo, useState } from "react"
import type { AdminDocument } from "@/types/admin"
import { Button } from "@/components/ui/Button"
import { ApprovalStatusBadge } from "./ApprovalStatusBadge"

interface DocumentListProps {
  documents: AdminDocument[]
  selectedId: string | null
  onSelect: (id: string) => void
  onIngest?: (id: string) => void
  ingestingDocumentId?: string | null
  canIngest?: boolean
}

interface DocumentGroup {
  type: string
  docs: AdminDocument[]
  pendingCount: number
}

function groupDocuments(documents: AdminDocument[]): DocumentGroup[] {
  const byType = new Map<string, AdminDocument[]>()
  for (const doc of documents) {
    const key = doc.documentType || "Lainnya"
    const list = byType.get(key) ?? []
    list.push(doc)
    byType.set(key, list)
  }

  return Array.from(byType.entries())
    .map(([type, docs]) => ({
      type,
      docs,
      pendingCount: docs.reduce((sum, doc) => sum + doc.pendingChunkCount, 0),
    }))
    .sort((a, b) => {
      if (a.pendingCount !== b.pendingCount) return b.pendingCount - a.pendingCount
      return a.type.localeCompare(b.type)
    })
}

export function DocumentList({
  documents,
  selectedId,
  onSelect,
  onIngest,
  ingestingDocumentId,
  canIngest = false,
}: DocumentListProps) {
  const [query, setQuery] = useState("")
  const [expandedOverrides, setExpandedOverrides] = useState<Record<string, boolean>>({})

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return documents
    return documents.filter((doc) => doc.title.toLowerCase().includes(q))
  }, [documents, query])

  const groups = useMemo(() => groupDocuments(filtered), [filtered])
  const isSearching = query.trim().length > 0

  const toggleGroup = (type: string, defaultOpen: boolean) => {
    setExpandedOverrides((prev) => ({ ...prev, [type]: !(prev[type] ?? defaultOpen) }))
  }

  return (
    <div className="flex flex-col gap-3 md:sticky md:top-6 md:max-h-[calc(100vh-230px)]">
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Cari dokumen..."
        className="shrink-0 rounded-xl border border-hairline bg-surface-elevated px-3 py-2 text-sm text-ink placeholder:text-ink-muted focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
      />

      <div className="flex flex-col gap-3 overflow-y-auto pr-1">
        {groups.length === 0 && <p className="px-1 text-xs text-ink-muted">Tidak ada dokumen yang cocok.</p>}

        {groups.map((group) => {
          const defaultOpen = group.pendingCount > 0
          const isOpen = isSearching ? true : (expandedOverrides[group.type] ?? defaultOpen)

          return (
            <div key={group.type} className="flex flex-col gap-2">
              <button
                type="button"
                onClick={() => toggleGroup(group.type, defaultOpen)}
                className="flex items-center justify-between gap-2 rounded-xl px-1 py-1 text-left transition-colors duration-300 hover:bg-surface-elevated"
              >
                <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink">
                  <ChevronIcon className={`h-3 w-3 shrink-0 text-ink-muted transition-transform duration-200 ${isOpen ? "rotate-90" : ""}`} />
                  {group.type}
                  <span className="font-normal normal-case text-ink-muted">({group.docs.length})</span>
                </span>
                {group.pendingCount > 0 && (
                  <span className="shrink-0 rounded-full bg-warning/10 px-2 py-0.5 text-[11px] font-medium text-primary">
                    {group.pendingCount} pending
                  </span>
                )}
              </button>

              {isOpen && (
                <div className="flex flex-col gap-2">
                  {group.docs.map((doc) => (
                    <DocumentCard
                      key={doc.id}
                      doc={doc}
                      isSelected={doc.id === selectedId}
                      onSelect={onSelect}
                      onIngest={onIngest}
                      isIngesting={ingestingDocumentId === doc.id}
                      canIngest={canIngest}
                    />
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function DocumentCard({
  doc,
  isSelected,
  onSelect,
  onIngest,
  isIngesting,
  canIngest,
}: {
  doc: AdminDocument
  isSelected: boolean
  onSelect: (id: string) => void
  onIngest?: (id: string) => void
  isIngesting: boolean
  canIngest: boolean
}) {
  // chunkCount === 0 means this document was uploaded/synced but never
  // successfully chunked — the review queue will stay empty until it is.
  const needsIngestion = doc.chunkCount === 0

  return (
    <div
      className={`flex flex-col gap-2 rounded-2xl border px-4 py-3 transition-colors duration-300 ${
        isSelected ? "border-primary bg-surface-elevated" : "border-hairline bg-surface hover:bg-surface-elevated"
      }`}
    >
      <button type="button" onClick={() => onSelect(doc.id)} className="flex flex-col gap-2 text-left">
        <div className="flex items-start justify-between gap-2">
          <p className="text-sm font-semibold text-ink">{doc.title}</p>
          <ApprovalStatusBadge status={doc.status} />
        </div>
        {doc.pendingChunkCount > 0 && (
          <span className="text-xs font-medium text-primary">{doc.pendingChunkCount} chunk menunggu review</span>
        )}
      </button>

      {needsIngestion && canIngest && (
        <div className="flex items-center justify-between gap-2 border-t border-hairline pt-2">
          <span className="text-xs text-warning">Belum diproses — 0 chunk</span>
          <Button
            variant="secondary"
            disabled={isIngesting}
            onClick={() => onIngest?.(doc.id)}
            className="!px-3 !py-1 text-xs"
          >
            {isIngesting ? "Memproses…" : "Proses Dokumen"}
          </Button>
        </div>
      )}
    </div>
  )
}

function ChevronIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="M7.5 4.5l6 5.5-6 5.5" />
    </svg>
  )
}
