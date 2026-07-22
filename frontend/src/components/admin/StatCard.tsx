interface StatCardProps {
  label: string
  value: number | string
  tone?: "neutral" | "warning" | "success" | "danger"
}

const TONE_TEXT: Record<NonNullable<StatCardProps["tone"]>, string> = {
  neutral: "text-ink",
  warning: "text-warning",
  success: "text-success",
  danger: "text-danger",
}

export function StatCard({ label, value, tone = "neutral" }: StatCardProps) {
  return (
    <div className="flex flex-col gap-1 rounded-2xl border border-hairline bg-surface p-4 shadow-premium transition-colors duration-300">
      <p className={`font-display text-3xl font-extrabold ${TONE_TEXT[tone]}`}>{value}</p>
      <p className="text-xs font-medium text-ink-muted">{label}</p>
    </div>
  )
}
