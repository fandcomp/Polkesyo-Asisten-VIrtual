"use client"

import { useMemo } from "react"
import { StatCard } from "@/components/admin/StatCard"
import { SystemHealthPanel } from "@/components/admin/SystemHealthPanel"
import { DocumentTypeBreakdown } from "@/components/admin/DocumentTypeBreakdown"
import { BackendFeaturePreview } from "@/components/admin/BackendFeaturePreview"
import { DocumentSourceMonitorPanel } from "@/components/admin/DocumentSourceMonitorPanel"
import { AgentMonitorPanel } from "@/components/admin/AgentMonitorPanel"
import { useAdminData } from "@/lib/useAdminData"

export default function AdminMonitoringPage() {
  const { documents, chunksByDocument, selectedId, setSelectedId, statsSummary } = useAdminData()

  // Real backend-computed counts when available (live mode) — falls back to a client-side
  // estimate in demo mode, where `statsSummary` stays null since there's no backend to ask.
  const stats = useMemo(() => {
    if (statsSummary) {
      const approvedChunks = statsSummary.chunks.by_status["approved"] ?? 0
      return {
        total: statsSummary.documents.total,
        pending: statsSummary.documents.by_status["pending_review"] ?? 0,
        approved: approvedChunks,
        flagged: statsSummary.chunks.flagged,
        vectorCount: statsSummary.vector_index.count,
      }
    }

    const pendingDocs = documents.filter((d) => d.status === "pending_review").length
    const approvedDocs = documents.filter((d) => d.status === "approved" || d.status === "active").length
    const flaggedChunks = Object.values(chunksByDocument)
      .flat()
      .filter((c) => c.riskFlags.length > 0).length

    return {
      total: documents.length,
      pending: pendingDocs,
      approved: approvedDocs,
      flagged: flaggedChunks,
      vectorCount: null as number | null,
    }
  }, [documents, chunksByDocument, statsSummary])

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="Total Dokumen" value={stats.total} />
        <StatCard label="Menunggu Review" value={stats.pending} tone="warning" />
        <StatCard label="Chunk Disetujui" value={stats.approved} tone="success" />
        <StatCard label="Chunk Ter-flag Risiko" value={stats.flagged} tone="danger" />
      </div>
      {stats.vectorCount !== null && (
        <p className="text-xs text-ink-muted">
          Vektor ter-index di Chroma (koleksi aktif): <span className="font-semibold">{stats.vectorCount}</span>
          {" — "}jumlah ini yang sebenarnya menentukan apakah chat bisa menjawab, bukan status &quot;ok&quot; di health check.
        </p>
      )}

      <SystemHealthPanel />

      <div className="flex flex-col gap-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
          Dokumen Berdasarkan Jenis
        </p>
        <DocumentTypeBreakdown documents={documents} selectedId={selectedId} onSelect={setSelectedId} />
      </div>

      <DocumentSourceMonitorPanel />

      <AgentMonitorPanel />

      <BackendFeaturePreview />
    </div>
  )
}
