"use client"

import { useState } from "react"
import Link from "next/link"
import { ApiClient } from "@/lib/apiClient"
import { useAdminData } from "@/lib/useAdminData"
import { Button } from "@/components/ui/Button"

type ActionId = "indexing" | "graph"

interface ActionState {
  loading: boolean
  result?: string
  isError?: boolean
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  return "Terjadi kesalahan yang tidak diketahui"
}

export function BackendFeaturePreview() {
  const { mode, selectedId, documents } = useAdminData()
  const [actions, setActions] = useState<Record<ActionId, ActionState>>({
    indexing: { loading: false },
    graph: { loading: false },
  })

  const isLive = mode === "live"
  const selectedDoc = documents.find((d) => d.id === selectedId)

  const setAction = (id: ActionId, state: ActionState) => {
    setActions((prev) => ({ ...prev, [id]: state }))
  }

  const runAction = async (id: ActionId, run: () => Promise<string>) => {
    setAction(id, { loading: true })
    try {
      const result = await run()
      setAction(id, { loading: false, result })
    } catch (error: unknown) {
      setAction(id, { loading: false, result: getErrorMessage(error), isError: true })
    }
  }

  const handleIndexing = () =>
    runAction("indexing", async () => {
      const res = await ApiClient.runIndexing()
      if (res.error) throw new Error(res.error)
      const failed = res.errors?.length ? `, ${res.errors.length} gagal` : ""
      return `${res.indexed_count ?? 0} chunk ter-index ke koleksi aktif${failed}`
    })

  const handleGraph = () =>
    runAction("graph", async () => {
      if (!selectedId) throw new Error("Pilih dokumen terlebih dahulu")
      const res = await ApiClient.indexDocumentGraph(selectedId)
      if (res.error) throw new Error(res.error)
      return `Graph diperbarui: ${res.created_nodes ?? 0} node, ${res.created_relationships ?? 0} relasi`
    })

  const renderResult = (state: ActionState) => {
    if (!state.result) return null
    return (
      <p className={`text-xs ${state.isError ? "text-danger" : "text-success"}`}>{state.result}</p>
    )
  }

  return (
    <div className="rounded-2xl border border-hairline bg-surface p-4 shadow-premium transition-colors duration-300">
      <div className="mb-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">Aksi Backend</p>
        <p className="mt-1 text-xs text-ink-muted">
          {isLive
            ? "Jalankan proses backend langsung dari panel ini."
            : "Aksi dinonaktifkan — backend tidak terhubung."}
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-2 rounded-xl border border-hairline bg-surface-elevated p-3">
          <p className="text-sm font-semibold text-ink">Jalankan Indexing Vector</p>
          <p className="text-xs text-ink-muted">
            Indeks ulang seluruh chunk yang telah disetujui ke koleksi Chroma aktif.
          </p>
          <code className="text-xs text-primary">POST /admin/indexing/run</code>
          <Button
            variant="secondary"
            disabled={!isLive || actions.indexing.loading}
            onClick={handleIndexing}
            className="mt-1 self-start !py-1.5 text-xs"
          >
            {actions.indexing.loading ? "Menjalankan…" : "Jalankan Indexing"}
          </Button>
          {renderResult(actions.indexing)}
        </div>

        <div className="flex flex-col gap-2 rounded-xl border border-hairline bg-surface-elevated p-3">
          <p className="text-sm font-semibold text-ink">Indexing Knowledge Graph</p>
          <p className="text-xs text-ink-muted">
            Masukkan entitas dan relasi dokumen terpilih ke Neo4j.
            {selectedDoc ? ` Dokumen terpilih: ${selectedDoc.title}` : " Belum ada dokumen terpilih."}
          </p>
          <code className="text-xs text-primary">POST /admin/graph/index-document</code>
          <Button
            variant="secondary"
            disabled={!isLive || !selectedId || actions.graph.loading}
            onClick={handleGraph}
            className="mt-1 self-start !py-1.5 text-xs"
          >
            {actions.graph.loading ? "Menjalankan…" : "Index Dokumen Terpilih"}
          </Button>
          {renderResult(actions.graph)}
        </div>

        <div className="flex flex-col gap-2 rounded-xl border border-hairline bg-surface-elevated p-3">
          <p className="text-sm font-semibold text-ink">Review Chunk Visual</p>
          <p className="text-xs text-ink-muted">
            Tinjau chunk hasil ekstraksi gambar, diagram, atau tabel dari dokumen — kini ada di
            halaman Review Dokumen, di bawah antrean chunk teks untuk dokumen terpilih.
          </p>
          <code className="text-xs text-primary">{"GET /admin/visual-chunks/{document_id}/pending"}</code>
          <Link href="/admin" className="mt-1 self-start">
            <Button variant="secondary" className="!py-1.5 text-xs">
              Buka Review Dokumen
            </Button>
          </Link>
        </div>
      </div>
    </div>
  )
}
