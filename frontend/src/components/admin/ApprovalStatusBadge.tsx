import type { ChunkStatus, DocumentStatus } from "@/types/admin"

type Status = ChunkStatus | DocumentStatus

const STATUS_LABEL: Record<Status, string> = {
  discovered: "Ditemukan",
  downloaded: "Diunduh",
  extracted: "Diekstrak",
  chunked: "Dipecah",
  created: "Dibuat",
  summarized: "Diringkas",
  summary_drafted: "Draf Ringkasan",
  pending_review: "Menunggu Review",
  approved: "Disetujui",
  indexed: "Terindeks",
  active: "Aktif",
  rejected: "Ditolak",
  needs_revision: "Perlu Revisi",
  superseded: "Digantikan",
  archived: "Diarsipkan",
}

const STATUS_TONE: Record<Status, "neutral" | "warning" | "success" | "danger"> = {
  discovered: "neutral",
  downloaded: "neutral",
  extracted: "neutral",
  chunked: "neutral",
  created: "neutral",
  summarized: "neutral",
  summary_drafted: "warning",
  pending_review: "warning",
  approved: "success",
  indexed: "success",
  active: "success",
  rejected: "danger",
  needs_revision: "danger",
  superseded: "neutral",
  archived: "neutral",
}

const TONE_CLASSES: Record<"neutral" | "warning" | "success" | "danger", string> = {
  neutral: "border-hairline bg-surface-elevated text-ink-muted",
  warning: "border-gold/50 bg-warning/10 text-ink",
  success: "border-success/40 bg-success/10 text-success",
  danger: "border-danger-border bg-danger-bg text-danger",
}

export function ApprovalStatusBadge({ status }: { status: Status }) {
  const tone = STATUS_TONE[status]
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors duration-300 ${TONE_CLASSES[tone]}`}
    >
      {STATUS_LABEL[status]}
    </span>
  )
}
