"use client"

import { useState } from "react"
import { KnowledgeGraphPanel } from "@/components/admin/KnowledgeGraphPanel"
import { useAdminData } from "@/lib/useAdminData"

export default function AdminKnowledgeGraphPage() {
  const { documents, selectedId, setSelectedId } = useAdminData()
  const [scope, setScope] = useState<"document" | "global">("document")

  return (
    <div className="flex flex-col gap-4">
      <div>
        <p className="font-display text-lg font-bold text-ink">Knowledge Graph</p>
        <p className="text-sm text-ink-muted">
          Entitas dan relasi yang benar-benar ter-index di Neo4j — bukti bagaimana GraphRAG
          bekerja untuk dokumen yang sudah disetujui.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex gap-1 rounded-lg border border-hairline p-1">
          <button
            type="button"
            onClick={() => setScope("document")}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              scope === "document" ? "bg-primary text-white" : "text-ink-muted hover:text-ink"
            }`}
          >
            Per Dokumen
          </button>
          <button
            type="button"
            onClick={() => setScope("global")}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              scope === "global" ? "bg-primary text-white" : "text-ink-muted hover:text-ink"
            }`}
          >
            Semua Dokumen
          </button>
        </div>

        {scope === "document" && (
          <select
            value={selectedId ?? ""}
            onChange={(e) => setSelectedId(e.target.value)}
            className="rounded-md border border-hairline bg-surface px-3 py-1.5 text-sm text-ink"
          >
            <option value="" disabled>
              Pilih dokumen...
            </option>
            {documents.map((d) => (
              <option key={d.id} value={d.id}>
                {d.title}
              </option>
            ))}
          </select>
        )}
      </div>

      <KnowledgeGraphPanel documentId={scope === "document" ? selectedId : null} scope={scope} />
    </div>
  )
}
