"use client"

import { useEffect, useState } from "react"
import { Button } from "@/components/ui/Button"
import { Badge } from "@/components/ui/Badge"
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable"
import { ApiClient, type RetrievalEvaluationLogResponse } from "@/lib/apiClient"
import { useToast } from "@/components/ui/Toast"

const PAGE_SIZE = 20

// Raw chunk_type values match DocumentChunk.chunk_type / the retrieval_rows metadata built in
// chat_core.py (CLAUDE.md §38's visual-chunk union: text/image/table_image/diagram/
// scanned_region/mixed). Falls back to the raw value for any type not yet mapped.
const CHUNK_TYPE_LABEL: Record<string, string> = {
  text: "Teks",
  image: "Gambar",
  table_image: "Tabel (Gambar)",
  diagram: "Diagram",
  scanned_region: "Hasil Pindai",
  mixed: "Campuran",
}

function chunkTypeLabel(type: string): string {
  return CHUNK_TYPE_LABEL[type] ?? type
}

// Raw retrieval_source values match RetrievalEvaluationLog.retrieval_source (backend/app/db/
// models.py, "allowed: vector, graph, hybrid, visual_chunk, cache"). Falls back to the raw
// value for any source not yet mapped.
const RETRIEVAL_SOURCE_LABEL: Record<string, string> = {
  vector: "Vector RAG",
  graph: "GraphRAG",
  hybrid: "Hybrid",
  visual_chunk: "Chunk Visual",
  cache: "Cache",
}

function retrievalSourceLabel(source: string): string {
  return RETRIEVAL_SOURCE_LABEL[source] ?? source
}

export default function RetrievalLogsPage() {
  const { showToast } = useToast()
  const [items, setItems] = useState<RetrievalEvaluationLogResponse[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [traceId, setTraceId] = useState("")

  const load = async () => {
    setLoading(true)
    try {
      const result = await ApiClient.listRetrievalLogs({ traceId: traceId || undefined, limit: PAGE_SIZE, offset })
      setItems(result.items)
      setTotal(result.total)
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Gagal memuat log retrieval.", "error")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offset])

  const exportCsv = async () => {
    try {
      await ApiClient.downloadEvaluationExport(
        "retrieval",
        traceId ? { trace_id: traceId } : {},
        "retrieval_evaluation_logs.csv"
      )
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Gagal mengekspor CSV.", "error")
    }
  }

  const columns: DataTableColumn<RetrievalEvaluationLogResponse>[] = [
    { key: "rank", header: "Rank", render: (r) => `#${r.retrieval_rank}` },
    { key: "title", header: "Dokumen", render: (r) => r.document_title ?? r.document_id ?? "-" },
    { key: "page", header: "Halaman", render: (r) => r.page_number ?? "-" },
    { key: "type", header: "Tipe", render: (r) => chunkTypeLabel(r.chunk_type ?? "text") },
    { key: "source", header: "Sumber", render: (r) => retrievalSourceLabel(r.retrieval_source) },
    {
      key: "score",
      header: "Skor",
      render: (r) => (r.retrieval_score !== null ? r.retrieval_score.toFixed(3) : "-"),
    },
    {
      key: "selected",
      header: "Status",
      render: (r) =>
        r.selected_for_context ? (
          <Badge label="Dipakai" tone="success" />
        ) : (
          <Badge label={r.rejected_reason ?? "Ditolak"} tone="neutral" />
        ),
    },
  ]

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3 rounded-2xl border border-hairline bg-surface p-4 shadow-premium">
        <label className="flex flex-col gap-1 text-xs text-ink-muted">
          Trace ID
          <input
            value={traceId}
            onChange={(e) => setTraceId(e.target.value)}
            className="rounded-xl border border-hairline bg-background px-3 py-1.5 text-sm text-ink"
          />
        </label>
        <Button
          variant="secondary"
          onClick={() => {
            setOffset(0)
            void load()
          }}
        >
          Terapkan Filter
        </Button>
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
