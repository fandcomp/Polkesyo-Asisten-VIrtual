"use client"

import { useEffect, useState } from "react"
import { StatCard } from "@/components/admin/StatCard"
import { ApiClient, type EvaluationOverviewResponse } from "@/lib/apiClient"
import { useToast } from "@/components/ui/Toast"

function pct(v: number | null): string {
  return v === null ? "-" : `${(v * 100).toFixed(0)}%`
}

function ms(v: number | null): string {
  return v === null ? "-" : `${Math.round(v)} ms`
}

export default function EvaluationOverviewPage() {
  const { showToast } = useToast()
  const [overview, setOverview] = useState<EvaluationOverviewResponse | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    ApiClient.getEvaluationOverview()
      .then(setOverview)
      .catch((e: unknown) => showToast(e instanceof Error ? e.message : "Gagal memuat overview.", "error"))
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (loading) return <p className="text-sm text-ink-muted">Memuat...</p>
  if (!overview) return <p className="text-sm text-danger">Data overview tidak tersedia.</p>

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
      <StatCard label="Total Log Chat" value={overview.total_chat_logs} />
      <StatCard label="Rata-rata Latensi" value={ms(overview.average_latency_ms)} />
      <StatCard label="P95 Latensi" value={ms(overview.p95_latency_ms)} />
      <StatCard label="Cakupan Sitasi" value={pct(overview.citation_coverage)} />
      <StatCard
        label="Tingkat Fallback"
        value={pct(overview.fallback_rate)}
        tone={overview.fallback_rate !== null && overview.fallback_rate > 0.3 ? "warning" : "neutral"}
      />
      <StatCard label="Rata-rata Precision@3" value={pct(overview.average_precision_at_3)} />
      <StatCard label="Rata-rata Recall@3" value={pct(overview.average_recall_at_3)} />
      <StatCard
        label="Tingkat Keberhasilan Serangan"
        value={pct(overview.attack_success_rate)}
        tone={overview.attack_success_rate !== null && overview.attack_success_rate > 0 ? "danger" : "success"}
      />
      <StatCard label="Rata-rata Skor ASQ" value={overview.average_asq_score?.toFixed(2) ?? "-"} />
      <StatCard
        label="Rata-rata Skor SUS"
        value={overview.average_sus_score?.toFixed(1) ?? "-"}
        tone={overview.average_sus_score !== null && overview.average_sus_score >= 68 ? "success" : "warning"}
      />
      <StatCard label="ACIF Diblokir" value={overview.acif_block_count} tone="danger" />
      <StatCard label="ACIF Peringatan" value={overview.acif_warning_count} tone="warning" />
    </div>
  )
}
