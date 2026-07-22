"use client"

import { useEffect, useState } from "react"
import { Button } from "@/components/ui/Button"
import { Badge } from "@/components/ui/Badge"
import {
  ApiClient,
  type ComparisonReportResponse,
  type EvaluationRunResponse,
  type MetricComparisonResponse,
} from "@/lib/apiClient"
import { useToast } from "@/components/ui/Toast"

const METRIC_LABELS: Record<string, string> = {
  precision_at_3: "Precision@3",
  recall_at_3: "Recall@3",
  faithfulness_score: "Faithfulness (LLM judge)",
  answer_relevance_score: "Answer Relevance (LLM judge)",
  total_latency_ms: "Latensi Total (ms)",
  citation_correct: "Sitasi Benar",
  fallback_correct: "Perilaku Fallback Benar",
  attack_success: "Serangan Berhasil (Security)",
}

function formatValue(value: number | null): string {
  if (value === null) return "-"
  return Number.isInteger(value) ? String(value) : value.toFixed(3)
}

function MetricRow({ metric }: { metric: MetricComparisonResponse }) {
  return (
    <tr className="border-b border-hairline">
      <td className="py-2 pr-3 font-medium text-ink">{METRIC_LABELS[metric.metric] ?? metric.metric}</td>
      <td className="py-2 pr-3 text-ink-muted">{metric.n_pairs}</td>
      <td className="py-2 pr-3 text-ink-muted">{formatValue(metric.mean_a)}</td>
      <td className="py-2 pr-3 text-ink-muted">{formatValue(metric.mean_b)}</td>
      <td className="py-2 pr-3 text-ink-muted">{formatValue(metric.mean_delta)}</td>
      <td className="py-2 pr-3 text-ink-muted">
        {metric.percent_change === null ? "-" : `${metric.percent_change.toFixed(1)}%`}
      </td>
      <td className="py-2 pr-3 text-ink-muted">{metric.test_name}</td>
      <td className="py-2 pr-3 text-ink-muted">{metric.p_value === null ? "-" : metric.p_value.toFixed(4)}</td>
      <td className="py-2 pr-3">
        {metric.significant === null ? (
          "-"
        ) : (
          <Badge
            label={metric.significant ? "Signifikan" : "Tidak signifikan"}
            tone={metric.significant ? "success" : "neutral"}
          />
        )}
      </td>
    </tr>
  )
}

export default function EvaluationComparePage() {
  const { showToast } = useToast()
  const [runs, setRuns] = useState<EvaluationRunResponse[]>([])
  const [loadingRuns, setLoadingRuns] = useState(true)
  const [runIdA, setRunIdA] = useState("")
  const [runIdB, setRunIdB] = useState("")
  const [comparing, setComparing] = useState(false)
  const [report, setReport] = useState<ComparisonReportResponse | null>(null)

  useEffect(() => {
    const load = async () => {
      setLoadingRuns(true)
      try {
        const result = await ApiClient.listEvaluationRuns({ limit: 50 })
        setRuns(result.items.filter((r) => r.status === "completed"))
      } catch (e: unknown) {
        showToast(e instanceof Error ? e.message : "Gagal memuat daftar evaluation runs.", "error")
      } finally {
        setLoadingRuns(false)
      }
    }
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const runCompare = async () => {
    if (!runIdA || !runIdB) {
      showToast("Pilih dua evaluation run yang selesai untuk dibandingkan.", "error")
      return
    }
    setComparing(true)
    try {
      const result = await ApiClient.compareEvaluationRuns(runIdA, runIdB)
      setReport(result)
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Gagal membandingkan evaluation runs.", "error")
    } finally {
      setComparing(false)
    }
  }

  const exportCsv = async () => {
    if (!runIdA || !runIdB) return
    try {
      await ApiClient.downloadEvaluationExport(
        "compare",
        { run_id_a: runIdA, run_id_b: runIdB },
        `acif_comparison_${runIdA}_vs_${runIdB}.csv`
      )
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Gagal mengunduh perbandingan.", "error")
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-2xl border border-hairline bg-surface p-4 shadow-premium">
        <p className="mb-1 font-display text-base font-bold text-ink">
          Perbandingan ACIF vs Tanpa ACIF
        </p>
        <p className="mb-4 text-xs text-ink-muted">
          Bandingkan dua evaluation run yang dijalankan atas gold-QA dataset yang sama (satu
          dengan <code>config_name=&quot;with_acif&quot;</code>, satu dengan{" "}
          <code>config_name=&quot;without_acif&quot;</code>) untuk menjawab rumusan masalah:
          apakah ACIF menghasilkan perbedaan yang signifikan secara statistik.
        </p>

        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-xs font-semibold text-ink-muted">Run A (mis. without_acif)</label>
            <select
              className="rounded-xl border border-hairline bg-surface-elevated px-3 py-2 text-sm text-ink"
              value={runIdA}
              onChange={(e) => setRunIdA(e.target.value)}
              disabled={loadingRuns}
            >
              <option value="">Pilih run...</option>
              {runs.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.run_name} {r.config_name ? `(${r.config_name})` : ""}
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-xs font-semibold text-ink-muted">Run B (mis. with_acif)</label>
            <select
              className="rounded-xl border border-hairline bg-surface-elevated px-3 py-2 text-sm text-ink"
              value={runIdB}
              onChange={(e) => setRunIdB(e.target.value)}
              disabled={loadingRuns}
            >
              <option value="">Pilih run...</option>
              {runs.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.run_name} {r.config_name ? `(${r.config_name})` : ""}
                </option>
              ))}
            </select>
          </div>

          <Button variant="primary" onClick={runCompare} disabled={comparing}>
            {comparing ? "Membandingkan..." : "Bandingkan"}
          </Button>

          {report && (
            <Button variant="secondary" onClick={exportCsv}>
              Export CSV
            </Button>
          )}
        </div>
      </div>

      {report && (
        <div className="rounded-2xl border border-hairline bg-surface p-4 shadow-premium">
          <p className="mb-1 font-display text-base font-bold text-ink">
            {report.config_name_a ?? "Run A"} vs {report.config_name_b ?? "Run B"}
          </p>
          <p className="mb-4 text-xs text-ink-muted">
            {report.n_paired_questions} soal berpasangan (question_id yang sama di kedua run).
            Uji Wilcoxon signed-rank untuk metrik kontinu, uji McNemar eksak untuk metrik biner.
            α = 0.05.
          </p>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-hairline text-ink-muted">
                  <th className="py-2 pr-3">Metrik</th>
                  <th className="py-2 pr-3">n</th>
                  <th className="py-2 pr-3">Rata-rata A</th>
                  <th className="py-2 pr-3">Rata-rata B</th>
                  <th className="py-2 pr-3">Delta (B-A)</th>
                  <th className="py-2 pr-3">% Perubahan</th>
                  <th className="py-2 pr-3">Uji</th>
                  <th className="py-2 pr-3">p-value</th>
                  <th className="py-2 pr-3">Hasil</th>
                </tr>
              </thead>
              <tbody>
                {report.metrics.map((m) => (
                  <MetricRow key={m.metric} metric={m} />
                ))}
                {report.attack_success && <MetricRow metric={report.attack_success} />}
              </tbody>
            </table>
          </div>

          {report.attack_success === null && (
            <p className="mt-3 text-xs text-ink-muted">
              Tidak ada soal kategori Security berpasangan pada kedua run — attack_success_rate
              tidak dapat dihitung.
            </p>
          )}
        </div>
      )}
    </div>
  )
}
