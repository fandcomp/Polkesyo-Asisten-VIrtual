"use client"

import { useEffect, useState } from "react"
import { Button } from "@/components/ui/Button"
import { StatCard } from "@/components/admin/StatCard"
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable"
import { ApiClient, type AsqResponseRecord, type AsqSummaryResponse } from "@/lib/apiClient"
import { useToast } from "@/components/ui/Toast"

const PAGE_SIZE = 20

export default function AsqResultsPage() {
  const { showToast } = useToast()
  const [summary, setSummary] = useState<AsqSummaryResponse | null>(null)
  const [items, setItems] = useState<AsqResponseRecord[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    try {
      const [summaryResult, listResult] = await Promise.all([
        ApiClient.getAsqSummary(),
        ApiClient.listAsqResponses({ limit: PAGE_SIZE, offset }),
      ])
      setSummary(summaryResult)
      setItems(listResult.items)
      setTotal(listResult.total)
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Gagal memuat hasil ASQ.", "error")
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
      await ApiClient.downloadEvaluationExport("asq", {}, "asq_responses.csv")
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Gagal mengekspor CSV.", "error")
    }
  }

  const columns: DataTableColumn<AsqResponseRecord>[] = [
    { key: "participant", header: "Partisipan", render: (r) => r.participant_code },
    { key: "scenario", header: "Skenario", render: (r) => r.scenario_code },
    { key: "asq1", header: "ASQ1", render: (r) => r.asq_1 },
    { key: "asq2", header: "ASQ2", render: (r) => r.asq_2 },
    { key: "asq3", header: "ASQ3", render: (r) => r.asq_3 },
    { key: "avg", header: "Rata-rata", render: (r) => r.average_score.toFixed(2) },
    {
      key: "created_at",
      header: "Waktu",
      render: (r) => (r.created_at ? new Date(r.created_at).toLocaleString("id-ID") : "-"),
    },
  ]

  return (
    <div className="flex flex-col gap-4">
      {summary && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatCard label="Total Respon" value={summary.total_responses} />
          <StatCard
            label="Rata-rata ASQ"
            value={summary.overall_average !== null ? summary.overall_average.toFixed(2) : "-"}
          />
          <StatCard label="ASQ1 (Kemudahan)" value={summary.item_averages.asq_1?.toFixed(2) ?? "-"} />
          <StatCard label="ASQ3 (Info Pendukung)" value={summary.item_averages.asq_3?.toFixed(2) ?? "-"} />
        </div>
      )}

      {summary && summary.by_scenario.length > 0 && (
        <div className="rounded-2xl border border-hairline bg-surface p-4 shadow-premium">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-muted">Rata-rata per Skenario</p>
          <ul className="flex flex-col gap-1 text-sm text-ink">
            {summary.by_scenario.map((s) => (
              <li key={s.scenario_code} className="flex justify-between">
                <span>{s.scenario_code}</span>
                <span>{s.average_score.toFixed(2)} ({s.count} respon)</span>
              </li>
            ))}
          </ul>
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
