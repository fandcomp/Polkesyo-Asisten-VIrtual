"use client"

import { useEffect, useMemo, useState } from "react"
import { Badge } from "@/components/ui/Badge"
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable"
import { ApiClient, type GoldQaQuestionResponse } from "@/lib/apiClient"
import { useToast } from "@/components/ui/Toast"

const BEHAVIOR_TONE: Record<string, "success" | "warning" | "danger"> = {
  answer: "success",
  fallback: "warning",
  block_or_fallback: "danger",
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

/** Read-only catalog of the gold-QA question set itself (question text, category, expected
 * behavior, pinned ground truth) — separate from every results-focused evaluation page
 * (Overview, Runs, Log Teknis, etc.), which stay exactly as they were. Someone who only
 * wants evaluation results never needs to open this tab. */
export default function GoldQaDatasetPage() {
  const { showToast } = useToast()
  const [questions, setQuestions] = useState<GoldQaQuestionResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [categoryFilter, setCategoryFilter] = useState("")

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      try {
        const result = await ApiClient.getGoldQaDataset()
        setQuestions(Object.values(result).sort((a, b) => a.id.localeCompare(b.id)))
      } catch (e: unknown) {
        showToast(e instanceof Error ? e.message : "Gagal memuat dataset gold-QA.", "error")
      } finally {
        setLoading(false)
      }
    }
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const categories = useMemo(
    () => Array.from(new Set(questions.map((q) => q.category).filter((c): c is string => Boolean(c)))).sort(),
    [questions]
  )

  const filtered = useMemo(
    () => (categoryFilter ? questions.filter((q) => q.category === categoryFilter) : questions),
    [questions, categoryFilter]
  )

  const columns: DataTableColumn<GoldQaQuestionResponse>[] = [
    { key: "id", header: "ID", render: (q) => q.id },
    { key: "category", header: "Kategori", render: (q) => q.category ?? "-" },
    { key: "question", header: "Pertanyaan", render: (q) => <span className="max-w-md">{q.question}</span> },
    {
      key: "behavior",
      header: "Perilaku Diharapkan",
      render: (q) => <Badge label={behaviorLabel(q.expected_behavior)} tone={BEHAVIOR_TONE[q.expected_behavior] ?? "warning"} />,
    },
    {
      key: "ground_truth",
      header: "Ground Truth",
      render: (q) =>
        q.expected_chunk_ids.length > 0 || q.expected_document_ids.length > 0 ? (
          <Badge label={`${q.expected_chunk_ids.length || q.expected_document_ids.length} dipin`} tone="success" />
        ) : (
          <span className="text-ink-muted">-</span>
        ),
    },
  ]

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-hairline bg-surface p-4 shadow-premium">
        <p className="text-sm text-ink-muted">
          {questions.length} pertanyaan pada backend/app/evaluation/gold_qa_dataset.jsonl — dievaluasi setiap kali
          sebuah Evaluation Run dijalankan.
        </p>
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="ml-auto rounded-xl border border-hairline bg-background px-3 py-1.5 text-sm text-ink"
        >
          <option value="">Semua kategori</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </div>

      <DataTable columns={columns} rows={filtered} rowKey={(q) => q.id} loading={loading} />
    </div>
  )
}
