"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { Button } from "@/components/ui/Button"
import { Badge } from "@/components/ui/Badge"
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable"
import {
  ApiClient,
  type EvaluationResultResponse,
  type EvaluationRunResponse,
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

export default function EvaluationRunsPage() {
  const { showToast } = useToast()
  const [runs, setRuns] = useState<EvaluationRunResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [triggering, setTriggering] = useState(false)
  const [selectedRun, setSelectedRun] = useState<
    { run: EvaluationRunResponse; results: EvaluationResultResponse[] } | null
  >(null)

  const load = async () => {
    setLoading(true)
    try {
      const result = await ApiClient.listEvaluationRuns()
      setRuns(result.items)
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Gagal memuat evaluation runs.", "error")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const trigger = async (configName: "with_acif" | "without_acif") => {
    setTriggering(true)
    try {
      await ApiClient.triggerEvaluationRun(`gold_qa_run_${configName}_${Date.now()}`, {
        configName,
        ablationDisableAcif: configName === "without_acif",
      })
      showToast("Evaluation run dimulai di background.")
      setTimeout(() => void load(), 2000)
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Gagal memulai evaluation run.", "error")
    } finally {
      setTriggering(false)
    }
  }

  const openDetail = async (runId: string) => {
    try {
      const detail = await ApiClient.getEvaluationRunDetail(runId)
      setSelectedRun(detail)
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Gagal memuat detail run.", "error")
    }
  }

  const columns: DataTableColumn<EvaluationRunResponse>[] = [
    { key: "name", header: "Nama Run", render: (r) => r.run_name },
    { key: "type", header: "Tipe", render: (r) => r.run_type },
    { key: "progress", header: "Progres", render: (r) => `${r.completed_questions}/${r.total_questions}` },
    { key: "status", header: "Status", render: (r) => <Badge label={RUN_STATUS_LABEL[r.status]} tone={RUN_STATUS_TONE[r.status]} /> },
    {
      key: "started",
      header: "Mulai",
      render: (r) => (r.started_at ? new Date(r.started_at).toLocaleString("id-ID") : "-"),
    },
    {
      key: "detail",
      header: "",
      render: (r) => (
        <Link
          href={`/admin/evaluation/runs/${r.id}`}
          className="text-xs font-semibold text-primary hover:underline"
          onClick={(e) => e.stopPropagation()}
        >
          Detail Lengkap →
        </Link>
      ),
    },
  ]

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between rounded-2xl border border-hairline bg-surface p-4 shadow-premium">
        <p className="text-sm text-ink-muted">
          Jalankan evaluasi terhadap gold QA dataset (backend/app/evaluation/gold_qa_dataset.jsonl).
          Jalankan kedua kondisi untuk membandingkan di halaman{" "}
          <Link href="/admin/evaluation/compare" className="text-primary hover:underline">
            Perbandingan ACIF
          </Link>
          .
        </p>
        <div className="flex gap-2">
          <Button variant="primary" onClick={() => void trigger("with_acif")} disabled={triggering}>
            {triggering ? "Memulai..." : "Jalankan (Dengan ACIF)"}
          </Button>
          <Button variant="secondary" onClick={() => void trigger("without_acif")} disabled={triggering}>
            {triggering ? "Memulai..." : "Jalankan Ablasi (Tanpa ACIF)"}
          </Button>
        </div>
      </div>

      <DataTable
        columns={columns}
        rows={runs}
        rowKey={(r) => r.id}
        loading={loading}
        onRowClick={(r) => void openDetail(r.id)}
      />

      {selectedRun && (
        <div className="fixed inset-0 z-40 flex justify-end bg-black/40" onClick={() => setSelectedRun(null)}>
          <div
            className="h-full w-full max-w-2xl overflow-y-auto bg-background p-6 shadow-premium"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-start justify-between">
              <p className="font-display text-lg font-bold text-ink">{selectedRun.run.run_name}</p>
              <Button variant="secondary" className="px-3 py-1.5 text-xs" onClick={() => setSelectedRun(null)}>
                Tutup
              </Button>
            </div>
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-hairline text-ink-muted">
                  <th className="py-2">Soal</th>
                  <th className="py-2">Kategori</th>
                  <th className="py-2">Diharapkan</th>
                  <th className="py-2">Fallback Benar</th>
                  <th className="py-2">Serangan Berhasil</th>
                  <th className="py-2">Latensi</th>
                </tr>
              </thead>
              <tbody>
                {selectedRun.results.map((res) => (
                  <tr key={res.id} className="border-b border-hairline">
                    <td className="py-2">{res.question_id}</td>
                    <td className="py-2">{res.category ?? "-"}</td>
                    <td className="py-2">{behaviorLabel(res.expected_behavior)}</td>
                    <td className="py-2">
                      {res.fallback_correct === null ? "-" : res.fallback_correct ? "Ya" : "Tidak"}
                    </td>
                    <td className="py-2">
                      {res.attack_success === null ? "-" : res.attack_success ? "Ya" : "Tidak"}
                    </td>
                    <td className="py-2">{res.total_latency_ms ?? "-"} ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
