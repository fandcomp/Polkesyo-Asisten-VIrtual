"use client"

import { useState } from "react"
import type { AdminChunk } from "@/types/admin"
import { Button } from "@/components/ui/Button"
import { ChunkReviewCard } from "./ChunkReviewCard"

interface ChunkReviewQueueProps {
  chunks: AdminChunk[]
  onApprove: (chunkId: string, adminSummary: string) => Promise<void>
  onReject: (chunkId: string, adminSummary: string) => Promise<void>
  onNeedsRevision: (chunkId: string, adminSummary: string) => Promise<void>
  onBulkApprove: () => void
}

export function ChunkReviewQueue({
  chunks,
  onApprove,
  onReject,
  onNeedsRevision,
  onBulkApprove,
}: ChunkReviewQueueProps) {
  const [confirmingBulk, setConfirmingBulk] = useState(false)
  const pendingCount = chunks.filter(
    (c) => c.status === "pending_review" || c.status === "summary_drafted"
  ).length

  const handleBulkClick = () => {
    if (!confirmingBulk) {
      setConfirmingBulk(true)
      return
    }
    onBulkApprove()
    setConfirmingBulk(false)
  }

  if (chunks.length === 0) {
    return (
      <p className="rounded-2xl border border-hairline bg-surface-elevated p-6 text-center text-sm text-ink-muted">
        Tidak ada chunk untuk dokumen ini.
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-ink-muted">
          <span className="font-semibold text-ink">{pendingCount}</span> dari {chunks.length} chunk menunggu review
        </p>
        {pendingCount > 0 && (
          <div className="flex items-center gap-2">
            {confirmingBulk && (
              <button
                type="button"
                onClick={() => setConfirmingBulk(false)}
                className="text-xs text-ink-muted underline"
              >
                Batal
              </button>
            )}
            <Button variant={confirmingBulk ? "danger" : "secondary"} onClick={handleBulkClick}>
              {confirmingBulk ? "Konfirmasi setujui semua?" : "Setujui Semua"}
            </Button>
          </div>
        )}
      </div>

      {chunks.map((chunk) => (
        <ChunkReviewCard
          key={chunk.id}
          chunk={chunk}
          onApprove={onApprove}
          onReject={onReject}
          onNeedsRevision={onNeedsRevision}
        />
      ))}
    </div>
  )
}
