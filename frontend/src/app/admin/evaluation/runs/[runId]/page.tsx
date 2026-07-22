"use client"

import { useEffect, useMemo, useState } from "react"
import { useParams } from "next/navigation"
import Link from "next/link"
import { Button } from "@/components/ui/Button"
import { Badge } from "@/components/ui/Badge"
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable"
import { AcifGateTimeline } from "@/components/admin/AcifGateTimeline"
import {
  ApiClient,
  type ChatLogDetailResponse,
  type EvaluationResultResponse,
  type EvaluationRunResponse,
  type GoldQaQuestionResponse,
} from "@/lib/apiClient"
import { useToast } from "@/components/ui/Toast"

const RUN_STATUS_TONE: Record<EvaluationRunResponse["status"], "neutral" | "success" | "warning" | "danger"> = {
  pending: "neutral",
  running: "warning",
  completed: "success",
  failed: "danger",
  cancelled: "neutral",
}

// EvaluationRunResponse["status"] values — matches the enum backing EvaluationRun.status.
const RUN_STATUS_LABEL: Record<EvaluationRunResponse["status"], string> = {
  pending: "Menunggu",
  running: "Berjalan",
  completed: "Selesai",
  failed: "Gagal",
  cancelled: "Dibatalkan",
}

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

// Raw expected_behavior values match GoldQaQuestion.expected_behavior
// (backend/app/evaluation/gold_qa_dataset.jsonl) — the only 3 values ever used. Falls back to
// the raw value for any behavior not yet mapped, so nothing ever renders blank.
const BEHAVIOR_LABEL: Record<string, string> = {
  answer: "Harus Dijawab",
  fallback: "Harus Fallback",
  block_or_fallback: "Harus Diblokir/Fallback",
}

function behaviorLabel(behavior: string): string {
  return BEHAVIOR_LABEL[behavior] ?? behavior
}

function formatPercent(value: number | null, count: number): string {
  if (value === null || count === 0) return "- (n=0)"
  return `${(value * 100).toFixed(0)}% (n=${count})`
}

/** Average of a nullable numeric field across results, ignoring nulls — mirrors the
 * backend's SQL AVG() semantics (NULLs excluded, not treated as 0) so this page's summary
 * cards agree with /api/admin/evaluation/overview's methodology. Returns the average and
 * the count of non-null samples it was computed from, since a percentage without its
 * sample size is misleading on a small gold-QA dataset. */
function averageOf(
  results: EvaluationResultResponse[],
  field: "precision_at_3" | "recall_at_3"
): { avg: number | null; count: number } {
  const values = results.map((r) => r[field]).filter((v): v is number => v !== null)
  if (values.length === 0) return { avg: null, count: 0 }
  return { avg: values.reduce((a, b) => a + b, 0) / values.length, count: values.length }
}

function rateOf(
  results: EvaluationResultResponse[],
  field: "citation_present" | "citation_correct" | "fallback_correct" | "attack_success"
): { avg: number | null; count: number } {
  const values = results.map((r) => r[field]).filter((v): v is boolean => v !== null)
  if (values.length === 0) return { avg: null, count: 0 }
  return { avg: values.filter(Boolean).length / values.length, count: values.length }
}

export default function EvaluationRunDetailPage() {
  const params = useParams<{ runId: string }>()
  const runId = params.runId
  const { showToast } = useToast()

  const [run, setRun] = useState<EvaluationRunResponse | null>(null)
  const [results, setResults] = useState<EvaluationResultResponse[]>([])
  const [goldQa, setGoldQa] = useState<Record<string, GoldQaQuestionResponse>>({})
  const [loading, setLoading] = useState(true)

  const [selected, setSelected] = useState<EvaluationResultResponse | null>(null)
  const [traceDetail, setTraceDetail] = useState<ChatLogDetailResponse | null>(null)
  const [traceLoading, setTraceLoading] = useState(false)

  useEffect(() => {
    if (!runId) return
    const load = async () => {
      setLoading(true)
      try {
        const [runDetail, dataset] = await Promise.all([
          ApiClient.getEvaluationRunDetail(runId),
          ApiClient.getGoldQaDataset().catch(() => ({})),
        ])
        setRun(runDetail.run)
        setResults(runDetail.results)
        setGoldQa(dataset)
      } catch (e: unknown) {
        showToast(e instanceof Error ? e.message : "Gagal memuat detail run.", "error")
      } finally {
        setLoading(false)
      }
    }
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId])

  const openQuestionDetail = async (result: EvaluationResultResponse) => {
    setSelected(result)
    if (!result.trace_id) {
      setTraceDetail(null)
      return
    }
    setTraceLoading(true)
    try {
      const detail = await ApiClient.getChatLogDetail(result.trace_id)
      setTraceDetail(detail)
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Gagal memuat detail trace.", "error")
      setTraceDetail(null)
    } finally {
      setTraceLoading(false)
    }
  }

  const precision = useMemo(() => averageOf(results, "precision_at_3"), [results])
  const recall = useMemo(() => averageOf(results, "recall_at_3"), [results])
  const citationCoverage = useMemo(() => rateOf(results, "citation_present"), [results])
  const citationCorrectness = useMemo(() => rateOf(results, "citation_correct"), [results])
  const fallbackCorrectness = useMemo(() => rateOf(results, "fallback_correct"), [results])
  const attackSuccess = useMemo(() => rateOf(results, "attack_success"), [results])

  const columns: DataTableColumn<EvaluationResultResponse>[] = [
    { key: "question_id", header: "Soal", render: (r) => r.question_id },
    { key: "category", header: "Kategori", render: (r) => r.category ?? "-" },
    { key: "expected_behavior", header: "Diharapkan", render: (r) => behaviorLabel(r.expected_behavior) },
    {
      key: "precision",
      header: "Precision@3",
      render: (r) => (r.precision_at_3 === null ? "-" : `${(r.precision_at_3 * 100).toFixed(0)}%`),
    },
    {
      key: "recall",
      header: "Recall@3",
      render: (r) => (r.recall_at_3 === null ? "-" : `${(r.recall_at_3 * 100).toFixed(0)}%`),
    },
    {
      key: "citation",
      header: "Sitasi",
      render: (r) =>
        r.citation_present === null ? (
          "-"
        ) : (
          <Badge
            label={r.citation_correct ? "Benar" : r.citation_present ? "Ada, tidak cocok" : "Tidak ada"}
            tone={r.citation_correct ? "success" : r.citation_present ? "warning" : "neutral"}
          />
        ),
    },
    {
      key: "fallback_correct",
      header: "Perilaku Benar",
      render: (r) =>
        r.fallback_correct === null ? (
          "-"
        ) : (
          <Badge label={r.fallback_correct ? "Ya" : "Tidak"} tone={r.fallback_correct ? "success" : "danger"} />
        ),
    },
    {
      key: "attack_success",
      header: "Serangan Berhasil",
      render: (r) =>
        r.attack_success === null ? (
          "-"
        ) : (
          <Badge label={r.attack_success ? "Ya" : "Tidak"} tone={r.attack_success ? "danger" : "success"} />
        ),
    },
    { key: "latency", header: "Latensi Total", render: (r) => (r.total_latency_ms !== null ? `${r.total_latency_ms} ms` : "-") },
  ]

  const goldQuestion = selected ? goldQa[selected.question_id] : undefined

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <Link href="/admin/evaluation/runs" className="text-xs text-primary hover:underline">
          ← Kembali ke daftar run
        </Link>
      </div>

      {run && (
        <div className="rounded-2xl border border-hairline bg-surface p-4 shadow-premium">
          <div className="mb-3 flex items-start justify-between">
            <div>
              <p className="font-display text-lg font-bold text-ink">{run.run_name}</p>
              <p className="text-xs text-ink-muted">
                {run.completed_questions}/{run.total_questions} soal · dibuat{" "}
                {run.created_at ? new Date(run.created_at).toLocaleString("id-ID") : "-"}
              </p>
            </div>
            <Badge label={RUN_STATUS_LABEL[run.status]} tone={RUN_STATUS_TONE[run.status]} />
          </div>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <SummaryStat label="Precision@3 rata-rata" value={formatPercent(precision.avg, precision.count)} />
            <SummaryStat label="Recall@3 rata-rata" value={formatPercent(recall.avg, recall.count)} />
            <SummaryStat label="Cakupan Sitasi" value={formatPercent(citationCoverage.avg, citationCoverage.count)} />
            <SummaryStat label="Sitasi Benar" value={formatPercent(citationCorrectness.avg, citationCorrectness.count)} />
            <SummaryStat label="Perilaku Benar" value={formatPercent(fallbackCorrectness.avg, fallbackCorrectness.count)} />
            <SummaryStat label="Serangan Berhasil" value={formatPercent(attackSuccess.avg, attackSuccess.count)} />
          </div>
          <p className="mt-3 text-xs text-ink-muted">
            Angka &ldquo;n&rdquo; adalah jumlah soal yang memiliki ground truth/kategori terkait untuk metrik tersebut — bukan
            seluruh soal. Klik satu baris pada tabel di bawah untuk melihat detail lengkap per pertanyaan.
          </p>
        </div>
      )}

      <DataTable
        columns={columns}
        rows={results}
        rowKey={(r) => r.id}
        loading={loading}
        onRowClick={openQuestionDetail}
      />

      {selected && (
        <div className="fixed inset-0 z-40 flex justify-end bg-black/40" onClick={() => setSelected(null)}>
          <div
            className="h-full w-full max-w-2xl overflow-y-auto bg-background p-6 shadow-premium"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-start justify-between">
              <div>
                <p className="font-display text-lg font-bold text-ink">{selected.question_id}</p>
                <p className="text-xs text-ink-muted">{selected.trace_id ?? "tidak ada trace (timeout)"}</p>
              </div>
              <Button variant="secondary" className="px-3 py-1.5 text-xs" onClick={() => setSelected(null)}>
                Tutup
              </Button>
            </div>

            <div className="flex flex-col gap-5">
              {goldQuestion && (
                <section>
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-muted">Pertanyaan Gold-QA</p>
                  <p className="text-sm text-ink">{goldQuestion.question}</p>
                  {goldQuestion.expected_answer && (
                    <p className="mt-1 text-xs text-ink-muted">Jawaban acuan: {goldQuestion.expected_answer}</p>
                  )}
                </section>
              )}

              <section className="grid grid-cols-2 gap-3 text-xs text-ink-muted">
                <div>Precision@3: <span className="text-ink">{selected.precision_at_3 ?? "-"}</span></div>
                <div>Recall@3: <span className="text-ink">{selected.recall_at_3 ?? "-"}</span></div>
                <div>Sitasi ada: <span className="text-ink">{String(selected.citation_present ?? "-")}</span></div>
                <div>Sitasi benar: <span className="text-ink">{String(selected.citation_correct ?? "-")}</span></div>
                <div>Perilaku benar: <span className="text-ink">{String(selected.fallback_correct ?? "-")}</span></div>
                <div>Serangan berhasil: <span className="text-ink">{String(selected.attack_success ?? "-")}</span></div>
                <div>Latensi total: <span className="text-ink">{selected.total_latency_ms ?? "-"} ms</span></div>
                <div>Latensi retrieval: <span className="text-ink">{selected.retrieval_latency_ms ?? "-"} ms</span></div>
              </section>

              {goldQuestion && (goldQuestion.expected_chunk_ids.length > 0 || goldQuestion.expected_document_ids.length > 0) && (
                <section>
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-muted">
                    Ground Truth (dipin di gold_qa_dataset.jsonl)
                  </p>
                  {goldQuestion.expected_document_ids.length > 0 && (
                    <p className="break-all text-xs text-ink-muted">
                      Dokumen: {goldQuestion.expected_document_ids.join(", ")}
                    </p>
                  )}
                  {goldQuestion.expected_chunk_ids.length > 0 && (
                    <p className="break-all text-xs text-ink-muted">
                      Chunk: {goldQuestion.expected_chunk_ids.join(", ")}
                    </p>
                  )}
                </section>
              )}

              {traceLoading ? (
                <p className="text-sm text-ink-muted">Memuat detail trace...</p>
              ) : traceDetail ? (
                <>
                  <section>
                    <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-muted">Jawaban Aktual</p>
                    <p className="whitespace-pre-wrap text-sm text-ink">{traceDetail.chat_log.final_answer ?? "-"}</p>
                    <p className="mt-1 text-xs text-ink-muted">
                      Status: {answerStatusLabel(traceDetail.chat_log.answer_status)}
                      {traceDetail.chat_log.fallback_reason ? ` — ${traceDetail.chat_log.fallback_reason}` : ""}
                    </p>
                  </section>

                  <section>
                    <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-muted">
                      Alur ACIF (Gate 1-5)
                    </p>
                    <AcifGateTimeline gates={traceDetail.acif_gates} />
                  </section>

                  <section>
                    <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-muted">
                      Chunk yang diambil vs ground truth ({traceDetail.retrieval.length})
                    </p>
                    <ul className="flex flex-col gap-1 text-xs text-ink">
                      {traceDetail.retrieval.map((r) => {
                        const isExpectedChunk = goldQuestion?.expected_chunk_ids.includes(r.chunk_id ?? "")
                        const isExpectedDoc = goldQuestion?.expected_document_ids.includes(r.document_id ?? "")
                        return (
                          <li
                            key={r.id}
                            className="flex items-center justify-between gap-2 rounded-xl border border-hairline px-3 py-2"
                          >
                            <span className="line-clamp-1">
                              #{r.retrieval_rank} {r.document_title ?? r.document_id ?? "?"}
                            </span>
                            <span className="flex shrink-0 gap-1">
                              {isExpectedChunk && <Badge label="Chunk cocok" tone="success" />}
                              {!isExpectedChunk && isExpectedDoc && <Badge label="Dok. cocok" tone="warning" />}
                              <Badge
                                label={r.selected_for_context ? "Dipakai" : "Ditolak"}
                                tone={r.selected_for_context ? "success" : "neutral"}
                              />
                            </span>
                          </li>
                        )
                      })}
                    </ul>
                  </section>
                </>
              ) : (
                <p className="text-sm text-ink-muted">Tidak ada trace tersimpan untuk soal ini (kemungkinan timeout saat run).</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function SummaryStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-hairline bg-surface-elevated p-3">
      <p className="text-xs text-ink-muted">{label}</p>
      <p className="font-display text-base font-bold text-ink">{value}</p>
    </div>
  )
}
