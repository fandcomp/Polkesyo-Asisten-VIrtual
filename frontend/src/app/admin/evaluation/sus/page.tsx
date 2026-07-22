"use client"

import { useEffect, useState } from "react"
import { Button } from "@/components/ui/Button"
import { StatCard } from "@/components/admin/StatCard"
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable"
import { ApiClient, type SusResponseRecord, type SusSummaryResponse } from "@/lib/apiClient"
import { useToast } from "@/components/ui/Toast"

const PAGE_SIZE = 20

export default function SusResultsPage() {
  const { showToast } = useToast()
  const [summary, setSummary] = useState<SusSummaryResponse | null>(null)
  const [items, setItems] = useState<SusResponseRecord[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    try {
      const [summaryResult, listResult] = await Promise.all([
        ApiClient.getSusSummary(),
        ApiClient.listSusResponses({ limit: PAGE_SIZE, offset }),
      ])
      setSummary(summaryResult)
      setItems(listResult.items)
      setTotal(listResult.total)
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Gagal memuat hasil SUS.", "error")
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
      await ApiClient.downloadEvaluationExport("sus", {}, "sus_responses.csv")
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Gagal mengekspor CSV.", "error")
    }
  }

  const columns: DataTableColumn<SusResponseRecord>[] = [
    { key: "participant", header: "Partisipan", render: (r) => r.participant_code },
    { key: "score", header: "Skor SUS", render: (r) => r.sus_score.toFixed(1) },
    {
      key: "created_at",
      header: "Waktu",
      render: (r) => (r.created_at ? new Date(r.created_at).toLocaleString("id-ID") : "-"),
    },
  ]

  return (
    <div className="flex flex-col gap-4">
      {summary && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <StatCard label="Total Respon" value={summary.total_responses} />
          <StatCard
            label="Rata-rata Skor SUS"
            value={summary.overall_average !== null ? summary.overall_average.toFixed(1) : "-"}
            tone={
              summary.overall_average !== null && summary.overall_average >= 68 ? "success" : "warning"
            }
          />
          <StatCard label="Jumlah Partisipan" value={summary.by_participant.length} />
        </div>
      )}

      {summary && (
        <div className="rounded-2xl border border-hairline bg-surface p-4 shadow-premium">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-muted">Rata-rata per Item</p>
          <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm text-ink sm:grid-cols-5">
            {Object.entries(summary.item_averages).map(([key, value]) => (
              <div key={key} className="flex justify-between">
                <span className="text-ink-muted">{key.toUpperCase()}</span>
                <span>{value !== null ? value.toFixed(2) : "-"}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex justify-end">
        <Button variant="primary" onClick={exportCsv}>
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
