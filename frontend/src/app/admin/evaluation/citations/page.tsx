"use client"

import { useEffect, useState } from "react"
import { Button } from "@/components/ui/Button"
import { Badge } from "@/components/ui/Badge"
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable"
import { ApiClient, type CitationEvaluationLogResponse } from "@/lib/apiClient"
import { useToast } from "@/components/ui/Toast"

const PAGE_SIZE = 20

// Raw citation_type values match CitationEvaluationLog.citation_type (backend/app/db/models.py,
// "allowed: text, graph, visual_chunk, table, mixed"). Falls back to the raw value for any type
// not yet mapped, so nothing ever renders blank.
const CITATION_TYPE_LABEL: Record<string, string> = {
  text: "Teks",
  graph: "Graf",
  visual_chunk: "Chunk Visual",
  table: "Tabel",
  mixed: "Campuran",
}

function citationTypeLabel(type: string): string {
  return CITATION_TYPE_LABEL[type] ?? type
}

export default function CitationLogsPage() {
  const { showToast } = useToast()
  const [items, setItems] = useState<CitationEvaluationLogResponse[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [traceId, setTraceId] = useState("")

  const load = async () => {
    setLoading(true)
    try {
      const result = await ApiClient.listCitationLogs({ traceId: traceId || undefined, limit: PAGE_SIZE, offset })
      setItems(result.items)
      setTotal(result.total)
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Gagal memuat log sitasi.", "error")
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
        "citations",
        traceId ? { trace_id: traceId } : {},
        "citation_evaluation_logs.csv"
      )
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Gagal mengekspor CSV.", "error")
    }
  }

  const columns: DataTableColumn<CitationEvaluationLogResponse>[] = [
    { key: "title", header: "Dokumen", render: (r) => r.document_title ?? r.document_id ?? "-" },
    { key: "page", header: "Halaman", render: (r) => r.page_number ?? "-" },
    { key: "type", header: "Tipe", render: (r) => citationTypeLabel(r.citation_type) },
    {
      key: "visual",
      header: "Visual",
      render: (r) => (r.is_visual_source ? <Badge label="Ya" tone="info" /> : "-"),
    },
    {
      key: "valid",
      header: "Valid",
      render: (r) =>
        r.is_valid === null ? (
          <Badge label="Belum diverifikasi" tone="neutral" />
        ) : r.is_valid ? (
          <Badge label="Valid" tone="success" />
        ) : (
          <Badge label="Tidak valid" tone="danger" />
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
