"use client"

import type { AdminVisualChunk } from "@/types/admin"
import { VisualChunkReviewCard } from "./VisualChunkReviewCard"

interface VisualChunkReviewQueueProps {
  chunks: AdminVisualChunk[]
  onApprove: (chunkId: string, editedDescription: string) => Promise<void>
  onReject: (chunkId: string, reason: string) => Promise<void>
  onNeedsRevision: (chunkId: string, reason: string, editedDescription: string) => Promise<void>
}

export function VisualChunkReviewQueue({
  chunks,
  onApprove,
  onReject,
  onNeedsRevision,
}: VisualChunkReviewQueueProps) {
  const pendingCount = chunks.filter((c) => c.status === "pending_review").length

  if (chunks.length === 0) {
    return (
      <p className="rounded-2xl border border-hairline bg-surface-elevated p-6 text-center text-sm text-ink-muted">
        Tidak ada chunk visual (gambar/tabel/diagram) untuk dokumen ini.
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-ink-muted">
        <span className="font-semibold text-ink">{pendingCount}</span> dari {chunks.length} chunk
        visual menunggu review
      </p>

      {chunks.map((chunk) => (
        <VisualChunkReviewCard
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
