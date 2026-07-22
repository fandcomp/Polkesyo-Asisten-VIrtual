"use client"

import { useCallback, useEffect, useState } from "react"
import { ApiClient, type AgentRunResponse } from "@/lib/apiClient"
import { useAdminData } from "@/lib/useAdminData"

type PanelState =
  | { phase: "loading" }
  | { phase: "error"; message: string }
  | { phase: "loaded"; runs: AgentRunResponse[] }

const STATUS_STYLE: Record<string, string> = {
  success: "border-success/40 bg-success/10 text-success",
  completed: "border-success/40 bg-success/10 text-success",
  error: "border-danger-border bg-danger-bg text-danger",
  failed: "border-danger-border bg-danger-bg text-danger",
}
const DEFAULT_STATUS_STYLE = "border-hairline bg-surface-elevated text-ink-muted"

// AgentRunResponse.status only ever comes back as "success" | "error" (see BaseAgent.run in
// backend/app/agents/base_agent.py) — mapped here for a UI that is otherwise all-Indonesian.
// Falls back to the raw value for any status not yet mapped, so nothing ever renders blank.
const STATUS_LABEL: Record<string, string> = {
  success: "Berhasil",
  error: "Error",
}

function statusLabel(status: string): string {
  return STATUS_LABEL[status] ?? status
}

// AgentRunResponse.task_type values observed across agent invocations: "chat"
// (OrchestratorAgent), "ingestion" (IngestionService/DocumentIngestionAgent calls), and
// "scheduled_sync" (the periodic sync worker task — backend/app/workers/tasks.py).
const TASK_TYPE_LABEL: Record<string, string> = {
  chat: "Chat",
  ingestion: "Ingesti Dokumen",
  scheduled_sync: "Sinkronisasi Terjadwal",
}

function taskTypeLabel(taskType: string): string {
  return TASK_TYPE_LABEL[taskType] ?? taskType
}

export function AgentMonitorPanel() {
  const { mode } = useAdminData()
  const [state, setState] = useState<PanelState>({ phase: "loading" })
  const [selected, setSelected] = useState<AgentRunResponse | null>(null)

  const refresh = useCallback(async () => {
    setState({ phase: "loading" })
    try {
      const runs = await ApiClient.listAgentRuns(undefined, 50)
      setState({ phase: "loaded", runs })
    } catch (err: unknown) {
      setState({ phase: "error", message: err instanceof Error ? err.message : "Gagal memuat riwayat agent" })
    }
  }, [])

  useEffect(() => {
    if (mode === "live") void refresh()
  }, [mode, refresh])

  if (mode !== "live") {
    return (
      <div className="rounded-2xl border border-hairline bg-surface p-4 shadow-premium">
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">Riwayat Agent</p>
        <p className="mt-2 text-sm text-ink-muted">Hanya tersedia dalam mode live (backend terhubung).</p>
      </div>
    )
  }

  return (
    <div className="rounded-2xl border border-hairline bg-surface p-4 shadow-premium transition-colors duration-300">
      <div className="mb-3 flex items-center justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">Riwayat Agent</p>
        <div className="flex items-center gap-2">
          <p className="text-xs text-ink-muted">Sumber: GET /api/agent-runs</p>
          <button
            type="button"
            onClick={() => void refresh()}
            disabled={state.phase === "loading"}
            aria-label="Muat ulang riwayat agent"
            className="rounded-lg border border-hairline px-2 py-1 text-xs text-ink-muted transition-colors duration-300 hover:bg-surface-elevated hover:text-ink disabled:opacity-50"
          >
            Muat Ulang
          </button>
        </div>
      </div>

      {state.phase === "loading" && <p className="text-sm text-ink-muted">Memuat…</p>}
      {state.phase === "error" && <p className="text-sm text-danger">{state.message}</p>}
      {state.phase === "loaded" && state.runs.length === 0 && (
        <p className="text-sm text-ink-muted">Belum ada eksekusi agent tercatat.</p>
      )}
      {state.phase === "loaded" && state.runs.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead>
              <tr className="text-xs uppercase tracking-wide text-ink-muted">
                <th className="pb-2 pr-3 font-medium">Agent</th>
                <th className="pb-2 pr-3 font-medium">Tugas</th>
                <th className="pb-2 pr-3 font-medium">Status</th>
                <th className="pb-2 pr-3 font-medium">Latensi</th>
                <th className="pb-2 font-medium">Waktu</th>
              </tr>
            </thead>
            <tbody>
              {state.runs.map((run) => (
                <tr
                  key={run.id}
                  className="cursor-pointer border-t border-hairline hover:bg-surface-elevated"
                  onClick={() => setSelected(run)}
                >
                  <td className="py-2 pr-3 text-ink">{run.agent_name}</td>
                  <td className="py-2 pr-3 text-ink-muted">{taskTypeLabel(run.task_type)}</td>
                  <td className="py-2 pr-3">
                    <span
                      className={`rounded-full border px-2 py-0.5 text-xs ${STATUS_STYLE[run.status] ?? DEFAULT_STATUS_STYLE}`}
                    >
                      {statusLabel(run.status)}
                    </span>
                  </td>
                  <td className="py-2 pr-3 text-ink-muted">{run.latency_ms != null ? `${run.latency_ms} ms` : "—"}</td>
                  <td className="py-2 text-ink-muted">
                    {run.created_at ? new Date(run.created_at).toLocaleString("id-ID") : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selected && (
        <div className="mt-3 rounded-xl border border-hairline bg-surface-elevated p-3 text-sm">
          <div className="mb-2 flex items-center justify-between">
            <p className="font-semibold text-ink">
              {selected.agent_name} — {taskTypeLabel(selected.task_type)}
            </p>
            <button
              type="button"
              onClick={() => setSelected(null)}
              aria-label="Tutup detail agent"
              className="text-xs text-ink-muted hover:text-ink"
            >
              Tutup
            </button>
          </div>
          {selected.error_message && (
            <p className="mb-2 text-xs text-danger">Error: {selected.error_message}</p>
          )}
          <p className="mb-1 text-xs font-medium text-ink-muted">Input</p>
          <p className="mb-2 whitespace-pre-wrap text-xs text-ink">{selected.input_summary ?? "—"}</p>
          <p className="mb-1 text-xs font-medium text-ink-muted">Output</p>
          <p className="whitespace-pre-wrap text-xs text-ink">{selected.output_summary ?? "—"}</p>
        </div>
      )}
    </div>
  )
}
