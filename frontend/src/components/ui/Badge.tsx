export type BadgeTone = "neutral" | "success" | "warning" | "danger" | "info"

interface BadgeProps {
  label: string
  tone?: BadgeTone
}

const TONE_CLASSES: Record<BadgeTone, string> = {
  neutral: "bg-surface-elevated text-ink-muted border-hairline",
  success: "bg-success/10 text-success border-success/30",
  warning: "bg-warning/10 text-warning border-warning/30",
  danger: "bg-danger-bg text-danger border-danger-border",
  info: "bg-primary/10 text-primary border-primary/30",
}

/** Shared status pill — extracted from the tone-map pattern that was previously duplicated
 * in StatCard.tsx and ApprovalStatusBadge.tsx. Used for ACIF gate statuses (PASS/WARN/BLOCK/
 * FALLBACK/ERROR), fallback flags, and citation validity across the evaluation admin pages. */
export function Badge({ label, tone = "neutral" }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide ${TONE_CLASSES[tone]}`}
    >
      {label}
    </span>
  )
}

const GATE_STATUS_TONE: Record<string, BadgeTone> = {
  pass: "success",
  warn: "warning",
  block: "danger",
  fallback: "warning",
  error: "danger",
}

export function GateStatusBadge({ status }: { status: string }) {
  return <Badge label={status.toUpperCase()} tone={GATE_STATUS_TONE[status] ?? "neutral"} />
}
