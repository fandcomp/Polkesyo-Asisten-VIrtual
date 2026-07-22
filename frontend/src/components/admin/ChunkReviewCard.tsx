"use client"

import { useState } from "react"
import type { AdminChunk } from "@/types/admin"
import { Button } from "@/components/ui/Button"
import { ApprovalStatusBadge } from "./ApprovalStatusBadge"
import { ChunkEntityEditor } from "./ChunkEntityEditor"

type ChunkAction = "approve" | "reject" | "needs_revision"

// Raw risk_flags values are set by IngestionService (backend/app/services/ingestion_service.py)
// — currently only "data_conflict_detected" is ever appended to a text chunk. Falls back to
// the raw value for any flag not yet mapped, so nothing ever renders blank.
const RISK_FLAG_LABEL: Record<string, string> = {
  data_conflict_detected: "Terindikasi Konflik Data",
}

function riskFlagLabel(flag: string): string {
  return RISK_FLAG_LABEL[flag] ?? flag
}

interface ChunkReviewCardProps {
  chunk: AdminChunk
  onApprove: (chunkId: string, adminSummary: string) => Promise<void>
  onReject: (chunkId: string, adminSummary: string) => Promise<void>
  onNeedsRevision: (chunkId: string, adminSummary: string) => Promise<void>
}

export function ChunkReviewCard({ chunk, onApprove, onReject, onNeedsRevision }: ChunkReviewCardProps) {
  const [adminSummary, setAdminSummary] = useState(chunk.adminEditedSummary ?? chunk.llmSummaryDraft)
  // Tracks which button was clicked so it can show instant "in progress" feedback
  // instead of leaving the admin unsure whether their click registered while the
  // request round-trips (approval also triggers synchronous backend reindexing).
  const [pendingAction, setPendingAction] = useState<ChunkAction | null>(null)
  // Only approved/rejected are final. "needs_revision" must stay editable, otherwise the
  // admin can see the warning flag but has no way to fix and resubmit the chunk.
  const isDecided = chunk.status === "approved" || chunk.status === "rejected"

  const runAction = async (action: ChunkAction, handler: () => Promise<void>) => {
    if (pendingAction) return
    setPendingAction(action)
    try {
      await handler()
    } finally {
      setPendingAction(null)
    }
  }

  return (
    <div className="flex flex-col gap-4 rounded-2xl border border-hairline bg-surface p-5 shadow-premium transition-colors duration-300">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-medium text-ink-muted">
          {chunk.section ?? "Bagian tidak diketahui"}
          {chunk.page ? ` · Halaman ${chunk.page}` : ""}
        </p>
        <div className="flex items-center gap-2">
          {chunk.riskFlags.map((flag) => (
            <span
              key={flag}
              className="rounded-full border border-danger-border bg-danger-bg px-2.5 py-0.5 text-xs font-medium text-danger"
            >
              {riskFlagLabel(flag)}
            </span>
          ))}
          <ApprovalStatusBadge status={chunk.status} />
        </div>
      </div>

      <div className="flex flex-col gap-1">
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
          Teks Asli (tidak dapat diubah)
        </p>
        <p className="rounded-xl border border-hairline bg-surface-elevated p-3 text-sm text-ink">
          {chunk.originalText}
        </p>
      </div>

      <div className="flex flex-col gap-1">
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
          Draf Ringkasan LLM
        </p>
        <p className="rounded-xl border border-hairline bg-surface-elevated p-3 text-sm italic text-ink-muted">
          {chunk.llmSummaryDraft}
        </p>
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor={`summary-${chunk.id}`} className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
          Ringkasan Admin (dapat diedit)
        </label>
        <textarea
          id={`summary-${chunk.id}`}
          value={adminSummary}
          onChange={(e) => setAdminSummary(e.target.value)}
          disabled={isDecided}
          rows={3}
          className="rounded-xl border border-hairline bg-surface px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-60"
        />
      </div>

      <ChunkEntityEditor chunkId={chunk.id} readOnly={isDecided} />

      {!isDecided && (
        <div className="flex flex-wrap gap-2 border-t border-hairline pt-3">
          <Button
            variant="approve"
            disabled={pendingAction !== null}
            onClick={() => runAction("approve", () => onApprove(chunk.id, adminSummary))}
          >
            {pendingAction === "approve" ? "Menyimpan…" : "Setujui"}
          </Button>
          <Button
            variant="secondary"
            disabled={pendingAction !== null}
            onClick={() => runAction("needs_revision", () => onNeedsRevision(chunk.id, adminSummary))}
          >
            {pendingAction === "needs_revision"
              ? "Menyimpan…"
              : chunk.status === "needs_revision"
                ? "Simpan & Tandai Perlu Revisi"
                : "Perlu Revisi"}
          </Button>
          <Button
            variant="danger"
            disabled={pendingAction !== null}
            onClick={() => runAction("reject", () => onReject(chunk.id, adminSummary))}
          >
            {pendingAction === "reject" ? "Menyimpan…" : "Tolak"}
          </Button>
        </div>
      )}
    </div>
  )
}
