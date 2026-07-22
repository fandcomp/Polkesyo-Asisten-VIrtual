"use client"

import { useState } from "react"
import type { AdminDocumentForm } from "@/types/admin"
import { Button } from "@/components/ui/Button"
import { ApprovalStatusBadge } from "./ApprovalStatusBadge"
import { ApiClient } from "@/lib/apiClient"

type DocumentFormAction = "approve" | "reject" | "needs_revision"

interface DocumentFormReviewCardProps {
  form: AdminDocumentForm
  onApprove: (formId: string, adminNotes: string) => Promise<void>
  onReject: (formId: string, reason: string) => Promise<void>
  onNeedsRevision: (formId: string, reason: string) => Promise<void>
}

const ZONE_TYPE_LABEL: Record<AdminDocumentForm["zoneType"], string> = {
  form_text: "Formulir (Teks)",
  form_vision: "Formulir (Hasil Pindai)",
}

export function DocumentFormReviewCard({
  form,
  onApprove,
  onReject,
  onNeedsRevision,
}: DocumentFormReviewCardProps) {
  const [notes, setNotes] = useState("")
  const [pendingAction, setPendingAction] = useState<DocumentFormAction | null>(null)
  const [downloadError, setDownloadError] = useState<string | null>(null)
  // Only approved/active/rejected are final. "needs_revision" must stay editable so the
  // admin has a way to fix and resubmit it, same reasoning as VisualChunkReviewCard.
  const isDecided = form.status === "approved" || form.status === "active" || form.status === "rejected"

  const runAction = async (action: DocumentFormAction, handler: () => Promise<void>) => {
    if (pendingAction) return
    setPendingAction(action)
    try {
      await handler()
    } finally {
      setPendingAction(null)
    }
  }

  const openDocument = async () => {
    setDownloadError(null)
    try {
      const url = await ApiClient.getDocumentFormDownloadBlobUrl(form.id)
      window.open(url, "_blank", "noopener,noreferrer")
    } catch (e: unknown) {
      setDownloadError(e instanceof Error ? e.message : "Gagal memuat dokumen formulir.")
    }
  }

  return (
    <div className="flex flex-col gap-4 rounded-2xl border border-hairline bg-surface p-5 shadow-premium transition-colors duration-300">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-medium text-ink-muted">
          {ZONE_TYPE_LABEL[form.zoneType]}
          {" · "}
          Halaman {form.sourcePageStart}
          {form.sourcePageEnd !== form.sourcePageStart ? `-${form.sourcePageEnd}` : ""}
        </p>
        <ApprovalStatusBadge status={form.status} />
      </div>

      <div className="flex flex-col gap-1">
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">Judul Formulir</p>
        <p className="rounded-xl border border-hairline bg-surface-elevated p-3 text-sm text-ink">
          {form.formTitle}
        </p>
      </div>

      <div className="flex flex-col gap-1">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
            Dokumen Word (.docx) Hasil Ekstraksi
          </p>
        </div>
        <Button variant="secondary" onClick={() => void openDocument()}>
          Buka Dokumen ↗
        </Button>
        {downloadError && <p className="text-xs text-danger">{downloadError}</p>}
      </div>

      {!isDecided && (
        <div className="flex flex-col gap-1">
          <label
            htmlFor={`notes-${form.id}`}
            className="text-xs font-semibold uppercase tracking-wide text-ink-muted"
          >
            Catatan Admin (opsional)
          </label>
          <input
            id={`notes-${form.id}`}
            type="text"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Alasan revisi/penolakan, atau catatan tambahan"
            className="rounded-xl border border-hairline bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-muted focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
      )}

      {!isDecided && (
        <div className="flex flex-wrap gap-2 border-t border-hairline pt-3">
          <Button
            variant="approve"
            disabled={pendingAction !== null}
            onClick={() => runAction("approve", () => onApprove(form.id, notes))}
          >
            {pendingAction === "approve" ? "Menyimpan…" : "Setujui"}
          </Button>
          <Button
            variant="secondary"
            disabled={pendingAction !== null}
            onClick={() => runAction("needs_revision", () => onNeedsRevision(form.id, notes))}
          >
            {pendingAction === "needs_revision"
              ? "Menyimpan…"
              : form.status === "needs_revision"
                ? "Simpan & Tandai Perlu Revisi"
                : "Perlu Revisi"}
          </Button>
          <Button
            variant="danger"
            disabled={pendingAction !== null}
            onClick={() => runAction("reject", () => onReject(form.id, notes))}
          >
            {pendingAction === "reject" ? "Menyimpan…" : "Tolak"}
          </Button>
        </div>
      )}
    </div>
  )
}
