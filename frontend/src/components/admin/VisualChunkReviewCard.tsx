"use client"

import { useEffect, useState } from "react"
import type { AdminVisualChunk } from "@/types/admin"
import { Button } from "@/components/ui/Button"
import { ApprovalStatusBadge } from "./ApprovalStatusBadge"
import { ApiClient } from "@/lib/apiClient"

type VisualChunkAction = "approve" | "reject" | "needs_revision"

interface VisualChunkReviewCardProps {
  chunk: AdminVisualChunk
  onApprove: (chunkId: string, editedDescription: string) => Promise<void>
  onReject: (chunkId: string, reason: string) => Promise<void>
  onNeedsRevision: (chunkId: string, reason: string, editedDescription: string) => Promise<void>
}

const CHUNK_TYPE_LABEL: Record<AdminVisualChunk["chunkType"], string> = {
  text: "Teks",
  image: "Gambar",
  table_image: "Tabel (Gambar)",
  diagram: "Diagram",
  scanned_region: "Hasil Pindai",
  mixed: "Campuran",
}

// Raw risk_flags values are set by VisionDescriptionService (backend/app/services/ingestion/
// vision_description_service.py) — the only 4 flags it ever appends. Falls back to the raw
// value for any flag not yet mapped, so nothing ever renders blank.
const RISK_FLAG_LABEL: Record<string, string> = {
  prompt_injection_detected: "Terindikasi Prompt Injection",
  unreadable_image: "Gambar Tidak Terbaca",
  high_blur: "Buram",
  low_resolution: "Resolusi Rendah",
}

function riskFlagLabel(flag: string): string {
  return RISK_FLAG_LABEL[flag] ?? flag
}

export function VisualChunkReviewCard({
  chunk,
  onApprove,
  onReject,
  onNeedsRevision,
}: VisualChunkReviewCardProps) {
  const [description, setDescription] = useState(chunk.rawVisualDescription)
  const [notes, setNotes] = useState("")
  // The raw endpoint URL requires admin Basic Auth, which a plain <img>/<a> can never send
  // — fetched once here (with the auth header attached) into a local blob URL instead.
  const [imageBlobUrl, setImageBlobUrl] = useState<string | null>(null)
  const [imageError, setImageError] = useState<string | null>(null)

  useEffect(() => {
    let objectUrl: string | null = null
    setImageError(null)
    ApiClient.getVisualChunkImageBlobUrl(chunk.id)
      .then((url) => {
        objectUrl = url
        setImageBlobUrl(url)
      })
      .catch((e: unknown) => setImageError(e instanceof Error ? e.message : "Gagal memuat gambar."))
    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [chunk.id])
  // Tracks which button was clicked so it can show instant "in progress" feedback
  // instead of leaving the admin unsure whether their click registered.
  const [pendingAction, setPendingAction] = useState<VisualChunkAction | null>(null)
  // Only approved/rejected are final. "needs_revision" must stay editable, otherwise the
  // admin can see the warning flag but has no way to fix and resubmit the chunk.
  const isDecided = chunk.status === "approved" || chunk.status === "rejected"

  const runAction = async (action: VisualChunkAction, handler: () => Promise<void>) => {
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
          {CHUNK_TYPE_LABEL[chunk.chunkType]}
          {chunk.page ? ` · Halaman ${chunk.page}` : ""}
          {typeof chunk.confidenceScore === "number"
            ? ` · Keyakinan ${Math.round(chunk.confidenceScore * 100)}%`
            : ""}
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
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
            Pratinjau Gambar/Tabel Asli
          </p>
          {imageBlobUrl && (
            <a
              href={imageBlobUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs font-semibold text-primary hover:underline"
            >
              Buka ukuran penuh ↗
            </a>
          )}
        </div>
        {/* No height cap: a screenshotted table can be tall or wide, and clipping it to a
         * fixed max-height defeats the point of reviewing it — admin needs to see the whole
         * thing at a readable size, not a thumbnail. object-contain still prevents distortion;
         * overflow-auto lets an oversized image scroll within the card instead of blowing out
         * the page layout. */}
        <div className="flex items-center justify-center overflow-auto rounded-xl border border-hairline bg-surface-elevated p-2">
          {imageError ? (
            <p className="p-4 text-sm text-danger">{imageError}</p>
          ) : imageBlobUrl ? (
            // eslint-disable-next-line @next/next/no-img-element -- internal admin preview, not a Next-optimized public asset
            <img
              src={imageBlobUrl}
              alt={`Pratinjau chunk visual halaman ${chunk.page ?? "?"}`}
              className="max-w-full rounded-lg object-contain"
            />
          ) : (
            <p className="p-4 text-sm text-ink-muted">Memuat gambar…</p>
          )}
        </div>
      </div>

      {chunk.visibleTextDraft && (
        <div className="flex flex-col gap-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
            Teks Terlihat pada Gambar (tidak dapat diubah)
          </p>
          <p className="rounded-xl border border-hairline bg-surface-elevated p-3 text-sm text-ink">
            {chunk.visibleTextDraft}
          </p>
        </div>
      )}

      <div className="flex flex-col gap-1">
        <label
          htmlFor={`vision-desc-${chunk.id}`}
          className="text-xs font-semibold uppercase tracking-wide text-ink-muted"
        >
          Deskripsi Visual (draf AI, dapat diedit)
        </label>
        <textarea
          id={`vision-desc-${chunk.id}`}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          disabled={isDecided}
          rows={3}
          className="rounded-xl border border-hairline bg-surface px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-60"
        />
      </div>

      {chunk.uncertaintyNotes && (
        <div className="flex flex-col gap-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
            Catatan Ketidakpastian AI
          </p>
          <p className="rounded-xl border border-hairline bg-surface-elevated p-3 text-sm italic text-ink-muted">
            {chunk.uncertaintyNotes}
          </p>
        </div>
      )}

      {!isDecided && (
        <div className="flex flex-col gap-1">
          <label
            htmlFor={`notes-${chunk.id}`}
            className="text-xs font-semibold uppercase tracking-wide text-ink-muted"
          >
            Catatan Admin (opsional)
          </label>
          <input
            id={`notes-${chunk.id}`}
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
            onClick={() => runAction("approve", () => onApprove(chunk.id, description))}
          >
            {pendingAction === "approve" ? "Menyimpan…" : "Setujui"}
          </Button>
          <Button
            variant="secondary"
            disabled={pendingAction !== null}
            onClick={() => runAction("needs_revision", () => onNeedsRevision(chunk.id, notes, description))}
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
            onClick={() => runAction("reject", () => onReject(chunk.id, notes))}
          >
            {pendingAction === "reject" ? "Menyimpan…" : "Tolak"}
          </Button>
        </div>
      )}
    </div>
  )
}
