"use client"

import { useEffect, useState } from "react"
import { Button } from "@/components/ui/Button"
import { GateStatusBadge } from "@/components/ui/Badge"
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable"
import { ApiClient, type AcifGateStatus, type AcifTraceLogResponse } from "@/lib/apiClient"
import { useToast } from "@/components/ui/Toast"

const PAGE_SIZE = 20
const STATUS_OPTIONS: (AcifGateStatus | "")[] = ["", "pass", "warn", "block", "fallback", "error"]

// Raw risk_level values match AcifTraceLog.risk_level (backend/app/db/models.py) — low/medium/
// high only (see ChatCoreService._gate1_risk_level and the gate_rows entries in chat_core.py).
// Falls back to the raw value for any level not yet mapped, so nothing ever renders blank.
const RISK_LEVEL_LABEL: Record<string, string> = {
  low: "Rendah",
  medium: "Sedang",
  high: "Tinggi",
}

function riskLevelLabel(level: string): string {
  return RISK_LEVEL_LABEL[level] ?? level
}

export default function AcifTracesPage() {
  const { showToast } = useToast()
  const [items, setItems] = useState<AcifTraceLogResponse[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [gateStatus, setGateStatus] = useState<AcifGateStatus | "">("")

  const load = async () => {
    setLoading(true)
    try {
      const result = await ApiClient.listAcifTraces({
        gateStatus: gateStatus || undefined,
        limit: PAGE_SIZE,
        offset,
      })
      setItems(result.items)
      setTotal(result.total)
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Gagal memuat ACIF traces.", "error")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offset, gateStatus])

  const exportCsv = async () => {
    try {
      await ApiClient.downloadEvaluationExport(
        "acif",
        gateStatus ? { gate_status: gateStatus } : {},
        "acif_trace_logs.csv"
      )
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Gagal mengekspor CSV.", "error")
    }
  }

  const columns: DataTableColumn<AcifTraceLogResponse>[] = [
    {
      key: "created_at",
      header: "Waktu",
      render: (r) => (r.created_at ? new Date(r.created_at).toLocaleString("id-ID") : "-"),
    },
    { key: "gate", header: "Gate", render: (r) => r.gate_name },
    { key: "status", header: "Status", render: (r) => <GateStatusBadge status={r.gate_status} /> },
    { key: "risk_level", header: "Risk Level", render: (r) => (r.risk_level ? riskLevelLabel(r.risk_level) : "-") },
    { key: "action", header: "Aksi", render: (r) => <span className="line-clamp-2 max-w-sm">{r.action_taken ?? "-"}</span> },
    { key: "latency", header: "Latensi", render: (r) => (r.latency_ms !== null ? `${r.latency_ms} ms` : "-") },
  ]

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3 rounded-2xl border border-hairline bg-surface p-4 shadow-premium">
        <label className="flex flex-col gap-1 text-xs text-ink-muted">
          Status gate
          <select
            value={gateStatus}
            onChange={(e) => {
              setOffset(0)
              setGateStatus(e.target.value as AcifGateStatus | "")
            }}
            className="rounded-xl border border-hairline bg-background px-3 py-1.5 text-sm text-ink"
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s ? s.toUpperCase() : "Semua"}
              </option>
            ))}
          </select>
        </label>
        <Button variant="primary" className="ml-auto" onClick={exportCsv}>
          Ekspor CSV
        </Button>
      </div>

      <DataTable
        columns={columns}
        rows={items}
        rowKey={(r) => r.id}
        loading={loading}
        pagination={{ total, limit: PAGE_SIZE, offset, onPageChange: setOffset }}
      />
    </div>
  )
}
