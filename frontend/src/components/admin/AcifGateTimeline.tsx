import { GateStatusBadge } from "@/components/ui/Badge"
import type { AcifTraceLogResponse } from "@/lib/apiClient"

// Raw risk_level values match AcifTraceLog.risk_level (backend/app/db/models.py), set via
// ChatCoreService's per-gate "risk_level" fields (low/medium/high only — see
// ChatCoreService._gate1_risk_level and the gate_rows entries in chat_core.py). Falls back to
// the raw value for any level not yet mapped, so nothing ever renders blank.
const RISK_LEVEL_LABEL: Record<string, string> = {
  low: "Rendah",
  medium: "Sedang",
  high: "Tinggi",
}

function riskLevelLabel(level: string): string {
  return RISK_LEVEL_LABEL[level] ?? level
}

/** Gate 1 → 2 → 3 → 4 → 5 timeline — safe audit view only (public_summary/admin_summary,
 * never a raw prompt or scoring formula; see AcifTraceLog's backend model docstring). */
export function AcifGateTimeline({ gates }: { gates: AcifTraceLogResponse[] }) {
  const sorted = [...gates].sort((a, b) => a.gate_number - b.gate_number)

  if (sorted.length === 0) {
    return <p className="text-sm text-ink-muted">Belum ada data trace ACIF untuk permintaan ini.</p>
  }

  return (
    <div className="flex flex-col gap-3">
      {sorted.map((gate) => (
        <div key={gate.id} className="rounded-2xl border border-hairline bg-surface p-4 shadow-premium">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="font-display text-sm font-bold text-ink">{gate.gate_name}</p>
            <GateStatusBadge status={gate.gate_status} />
          </div>
          <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-ink-muted sm:grid-cols-4">
            {gate.risk_level && (
              <div>
                <dt className="font-semibold uppercase tracking-wide">Risk level</dt>
                <dd className="text-ink">{riskLevelLabel(gate.risk_level)}</dd>
              </div>
            )}
            {gate.action_taken && (
              <div className="col-span-2">
                <dt className="font-semibold uppercase tracking-wide">Aksi</dt>
                <dd className="text-ink">{gate.action_taken}</dd>
              </div>
            )}
            {gate.latency_ms !== null && (
              <div>
                <dt className="font-semibold uppercase tracking-wide">Latensi</dt>
                <dd className="text-ink">{gate.latency_ms} ms</dd>
              </div>
            )}
          </dl>
          {gate.admin_summary && (
            <p className="mt-2 text-sm text-ink">{gate.admin_summary}</p>
          )}
        </div>
      ))}
    </div>
  )
}
