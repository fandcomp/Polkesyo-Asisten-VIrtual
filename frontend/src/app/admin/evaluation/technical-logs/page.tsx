"use client"

import { useEffect, useState } from "react"
import { Button } from "@/components/ui/Button"
import { Badge } from "@/components/ui/Badge"
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable"
import { AcifGateTimeline } from "@/components/admin/AcifGateTimeline"
import { ApiClient, type ChatEvaluationLogResponse, type ChatLogDetailResponse } from "@/lib/apiClient"
import { useToast } from "@/components/ui/Toast"

const PAGE_SIZE = 20

// Raw answer_status values match ChatEvaluationLog.answer_status (backend/app/db/models.py),
// set across ChatCoreService.process_message / OrchestratorAgent / AnswerComposerAgent — see
// chat_core.py's "_finalize" call sites for the authoritative list. Falls back to the raw
// value for any status not yet mapped, so nothing ever renders blank.
const ANSWER_STATUS_LABEL: Record<string, string> = {
  no_consent: "Belum Ada Persetujuan",
  rate_limited: "Dibatasi Laju",
  service_busy: "Layanan Sibuk",
  rejected_by_input_filter: "Ditolak Filter Input",
  out_of_domain: "Di Luar Cakupan",
  insufficient_context: "Konteks Tidak Cukup",
  error: "Error",
  service_unavailable: "Layanan Tidak Tersedia",
  answered: "Terjawab",
  fallback_enforced: "Fallback Diterapkan",
  verified: "Terverifikasi",
  verification_error: "Error Verifikasi",
}

function answerStatusLabel(status: string): string {
  return ANSWER_STATUS_LABEL[status] ?? status
}

export default function TechnicalLogsPage() {
  const { showToast } = useToast()
  const [items, setItems] = useState<ChatEvaluationLogResponse[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [participantCode, setParticipantCode] = useState("")
  const [scenarioCode, setScenarioCode] = useState("")
  const [fallbackOnly, setFallbackOnly] = useState(false)

  const [detail, setDetail] = useState<ChatLogDetailResponse | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await ApiClient.listChatLogs({
        participantCode: participantCode || undefined,
        scenarioCode: scenarioCode || undefined,
        fallbackTriggered: fallbackOnly ? true : undefined,
        limit: PAGE_SIZE,
        offset,
      })
      setItems(result.items)
      setTotal(result.total)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Gagal memuat log teknis.")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offset])

  const applyFilters = () => {
    setOffset(0)
    void load()
  }

  const openDetail = async (traceId: string) => {
    setDetailLoading(true)
    try {
      const result = await ApiClient.getChatLogDetail(traceId)
      setDetail(result)
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Gagal memuat detail trace.", "error")
    } finally {
      setDetailLoading(false)
    }
  }

  const exportCsv = async () => {
    try {
      await ApiClient.downloadEvaluationExport(
        "chat-logs",
        {
          ...(participantCode ? { participant_code: participantCode } : {}),
          ...(scenarioCode ? { scenario_code: scenarioCode } : {}),
        },
        "chat_evaluation_logs.csv"
      )
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Gagal mengekspor CSV.", "error")
    }
  }

  const columns: DataTableColumn<ChatEvaluationLogResponse>[] = [
    {
      key: "created_at",
      header: "Waktu",
      render: (r) => (r.created_at ? new Date(r.created_at).toLocaleString("id-ID") : "-"),
    },
    {
      key: "question",
      header: "Pertanyaan",
      render: (r) => <span className="line-clamp-1 max-w-xs">{r.user_question}</span>,
    },
    {
      key: "status",
      header: "Status",
      render: (r) => (
        <Badge label={answerStatusLabel(r.answer_status)} tone={r.fallback_triggered ? "warning" : "success"} />
      ),
    },
    { key: "latency", header: "Latensi", render: (r) => (r.total_latency_ms !== null ? `${r.total_latency_ms} ms` : "-") },
    { key: "model", header: "Model", render: (r) => r.model_used ?? "-" },
    {
      key: "scenario",
      header: "Skenario",
      render: (r) => r.scenario_code ?? <span className="text-ink-muted">publik</span>,
    },
  ]

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3 rounded-2xl border border-hairline bg-surface p-4 shadow-premium">
        <label className="flex flex-col gap-1 text-xs text-ink-muted">
          Kode partisipan
          <input
            value={participantCode}
            onChange={(e) => setParticipantCode(e.target.value)}
            className="rounded-xl border border-hairline bg-background px-3 py-1.5 text-sm text-ink"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-ink-muted">
          Kode skenario
          <input
            value={scenarioCode}
            onChange={(e) => setScenarioCode(e.target.value)}
            className="rounded-xl border border-hairline bg-background px-3 py-1.5 text-sm text-ink"
          />
        </label>
        <label className="flex items-center gap-2 pb-1.5 text-sm text-ink">
          <input type="checkbox" checked={fallbackOnly} onChange={(e) => setFallbackOnly(e.target.checked)} />
          Hanya fallback
        </label>
        <Button variant="secondary" onClick={applyFilters}>
          Terapkan Filter
        </Button>
        <Button variant="primary" className="ml-auto" onClick={exportCsv}>
          Ekspor CSV
        </Button>
      </div>

      {error && <p className="text-sm text-danger">{error}</p>}

      <DataTable
        columns={columns}
        rows={items}
        rowKey={(r) => r.trace_id}
        loading={loading}
        onRowClick={(r) => void openDetail(r.trace_id)}
        pagination={{ total, limit: PAGE_SIZE, offset, onPageChange: setOffset }}
      />

      {detail && (
        <div className="fixed inset-0 z-40 flex justify-end bg-black/40" onClick={() => setDetail(null)}>
          <div
            className="h-full w-full max-w-lg overflow-y-auto bg-background p-6 shadow-premium"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-start justify-between">
              <div>
                <p className="font-display text-lg font-bold text-ink">Detail Trace</p>
                <p className="text-xs text-ink-muted">{detail.chat_log.trace_id}</p>
              </div>
              <Button variant="secondary" className="px-3 py-1.5 text-xs" onClick={() => setDetail(null)}>
                Tutup
              </Button>
            </div>

            {detailLoading ? (
              <p className="text-sm text-ink-muted">Memuat...</p>
            ) : (
              <div className="flex flex-col gap-5">
                <section>
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-muted">Pertanyaan</p>
                  <p className="text-sm text-ink">{detail.chat_log.user_question}</p>
                </section>
                <section>
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-muted">Jawaban</p>
                  <p className="whitespace-pre-wrap text-sm text-ink">{detail.chat_log.final_answer ?? "-"}</p>
                </section>
                <section className="grid grid-cols-2 gap-3 text-xs text-ink-muted">
                  <div>Status: <span className="text-ink">{answerStatusLabel(detail.chat_log.answer_status)}</span></div>
                  <div>Latensi total: <span className="text-ink">{detail.chat_log.total_latency_ms} ms</span></div>
                  <div>Model: <span className="text-ink">{detail.chat_log.model_used ?? "-"}</span></div>
                  <div>Sitasi: <span className="text-ink">{detail.citations.length}</span></div>
                </section>
                <section>
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-muted">
                    Alur ACIF (Gate 1-5)
                  </p>
                  <AcifGateTimeline gates={detail.acif_gates} />
                </section>
                <section>
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-muted">
                    Chunk yang diambil ({detail.retrieval.length})
                  </p>
                  <ul className="flex flex-col gap-1 text-xs text-ink">
                    {detail.retrieval.map((r) => (
                      <li key={r.id} className="flex items-center justify-between rounded-xl border border-hairline px-3 py-2">
                        <span>#{r.retrieval_rank} {r.document_title ?? r.document_id ?? "?"}</span>
                        <Badge
                          label={r.selected_for_context ? "Dipakai" : "Ditolak"}
                          tone={r.selected_for_context ? "success" : "neutral"}
                        />
                      </li>
                    ))}
                  </ul>
                </section>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
