"use client"

import type { AdminDocumentForm } from "@/types/admin"
import { DocumentFormReviewCard } from "./DocumentFormReviewCard"

interface DocumentFormReviewQueueProps {
  forms: AdminDocumentForm[]
  onApprove: (formId: string, adminNotes: string) => Promise<void>
  onReject: (formId: string, reason: string) => Promise<void>
  onNeedsRevision: (formId: string, reason: string) => Promise<void>
}

export function DocumentFormReviewQueue({
  forms,
  onApprove,
  onReject,
  onNeedsRevision,
}: DocumentFormReviewQueueProps) {
  const pendingCount = forms.filter((f) => f.status === "pending_review").length

  if (forms.length === 0) {
    return (
      <p className="rounded-2xl border border-hairline bg-surface-elevated p-6 text-center text-sm text-ink-muted">
        Tidak ada formulir/lampiran hasil ekstraksi untuk dokumen ini.
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-ink-muted">
        <span className="font-semibold text-ink">{pendingCount}</span> dari {forms.length} formulir
        menunggu review
      </p>

      {forms.map((form) => (
        <DocumentFormReviewCard
          key={form.id}
          form={form}
          onApprove={onApprove}
          onReject={onReject}
          onNeedsRevision={onNeedsRevision}
        />
      ))}
    </div>
  )
}
