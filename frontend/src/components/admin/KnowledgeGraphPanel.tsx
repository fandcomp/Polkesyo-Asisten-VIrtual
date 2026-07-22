"use client"

import { useEffect, useRef, useState } from "react"
import { DataSet } from "vis-data"
import { Network, type Options } from "vis-network"
import { ApiClient, type KgGraphResponse } from "@/lib/apiClient"
import { useAdminData } from "@/lib/useAdminData"

// Color per entity type — deliberately close to Neo4j Browser's own default palette
// (distinct hue per label, circular nodes) so this reads as "the same graph" to anyone
// who has looked at the raw data in Neo4j Browser directly.
const TYPE_COLORS: Record<string, string> = {
  Document: "#4C8EDA",
  ProgramStudi: "#F16667",
  JalurPendaftaran: "#D9C8AE",
  TahapSeleksi: "#8DCC93",
  Persyaratan: "#FFC454",
  Jadwal: "#C990C0",
  Biaya: "#F79767",
}

const DEFAULT_COLOR = "#A5ABB6"

// Raw node `type` values are GraphService.ALLOWED_ENTITY_TYPES (PascalCase graph-schema
// identifiers) plus the synthetic "Document" node type graph_service.py emits for source
// documents — readable here as e.g. "Program Studi" instead of the technical "ProgramStudi"
// admins would otherwise see verbatim in the legend, tooltip, and selected-node panel. Falls
// back to the raw value for any type not yet mapped, so nothing ever renders blank.
const ENTITY_TYPE_LABEL: Record<string, string> = {
  Document: "Dokumen",
  ProgramStudi: "Program Studi",
  JalurPendaftaran: "Jalur Pendaftaran",
  TahapSeleksi: "Tahap Seleksi",
  Persyaratan: "Persyaratan",
  Jadwal: "Jadwal",
  Biaya: "Biaya",
}

function entityTypeLabel(type: string): string {
  return ENTITY_TYPE_LABEL[type] ?? type
}

function toVisData(graph: KgGraphResponse) {
  const nodes = new DataSet(
    graph.nodes.map((n) => ({
      id: n.id,
      label: n.label.length > 40 ? `${n.label.slice(0, 37)}...` : n.label,
      title: `${entityTypeLabel(n.type)}: ${n.label}`,
      color: TYPE_COLORS[n.type] ?? DEFAULT_COLOR,
      shape: n.type === "Document" ? "box" : "dot",
      size: n.type === "Document" ? 18 : 12,
    }))
  )
  const edges = new DataSet(
    graph.edges.map((e, i) => ({
      id: i,
      from: e.source,
      to: e.target,
      label: e.type === "MENTIONS" ? "" : e.type,
      arrows: "to",
      font: { size: 10, align: "middle" },
      color: { color: "#B8C2CC", opacity: 0.7 },
    }))
  )
  return { nodes, edges }
}

const NETWORK_OPTIONS: Options = {
  physics: {
    solver: "forceAtlas2Based",
    forceAtlas2Based: { gravitationalConstant: -60, springLength: 120, springConstant: 0.06 },
    stabilization: { iterations: 150 },
  },
  interaction: { hover: true, tooltipDelay: 100 },
  nodes: { borderWidth: 1, font: { color: "#1f2937", size: 12 } },
}

interface KnowledgeGraphPanelProps {
  documentId: string | null
  scope: "document" | "global"
}

export function KnowledgeGraphPanel({ documentId, scope }: KnowledgeGraphPanelProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const networkRef = useRef<Network | null>(null)
  const [selectedNode, setSelectedNode] = useState<{ label: string; type: string } | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isEmpty, setIsEmpty] = useState(false)
  const { mode } = useAdminData()

  useEffect(() => {
    if (mode !== "live") return
    if (scope === "document" && !documentId) return

    let cancelled = false
    setIsLoading(true)
    setError(null)

    const fetchGraph = scope === "document" && documentId
      ? ApiClient.getDocumentGraph(documentId)
      : ApiClient.getGlobalGraph()

    fetchGraph
      .then((graph) => {
        if (cancelled || !containerRef.current) return
        setIsEmpty(graph.nodes.length === 0)
        const { nodes, edges } = toVisData(graph)

        if (networkRef.current) {
          networkRef.current.destroy()
        }
        const network = new Network(containerRef.current, { nodes, edges }, NETWORK_OPTIONS)
        network.on("click", (params) => {
          if (params.nodes.length === 0) {
            setSelectedNode(null)
            return
          }
          const node = graph.nodes.find((n) => n.id === params.nodes[0])
          setSelectedNode(node ? { label: node.label, type: node.type } : null)
        })
        networkRef.current = network
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Gagal memuat graf")
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [documentId, scope, mode])

  useEffect(() => {
    return () => {
      networkRef.current?.destroy()
    }
  }, [])

  if (mode !== "live") {
    return (
      <div className="rounded-lg border border-hairline bg-surface p-6 text-sm text-ink-muted">
        Knowledge Graph hanya tersedia dalam mode live (backend terhubung).
      </div>
    )
  }

  if (scope === "document" && !documentId) {
    return (
      <div className="rounded-lg border border-hairline bg-surface p-6 text-sm text-ink-muted">
        Pilih dokumen terlebih dahulu untuk melihat graf pengetahuannya.
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-3 text-xs text-ink-muted">
        {Object.entries(TYPE_COLORS).map(([type, color]) => (
          <span key={type} className="flex items-center gap-1.5">
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: color }}
            />
            {entityTypeLabel(type)}
          </span>
        ))}
      </div>

      <div className="relative h-[480px] w-full rounded-lg border border-hairline bg-surface">
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center text-sm text-ink-muted">
            Memuat graf...
          </div>
        )}
        {error && (
          <div className="absolute inset-0 flex items-center justify-center p-4 text-center text-sm text-danger">
            {error}
          </div>
        )}
        {!isLoading && !error && isEmpty && (
          <div className="absolute inset-0 flex items-center justify-center p-4 text-center text-sm text-ink-muted">
            Belum ada entitas ter-index untuk cakupan ini. Jalankan &quot;Indexing Knowledge
            Graph&quot; di tab Monitoring setelah dokumen disetujui.
          </div>
        )}
        <div ref={containerRef} className="h-full w-full" />
      </div>

      {selectedNode && (
        <div className="rounded-lg border border-hairline bg-surface-elevated p-3 text-sm">
          <p className="font-semibold text-ink">{selectedNode.label}</p>
          <p className="text-xs text-ink-muted">Tipe: {entityTypeLabel(selectedNode.type)}</p>
        </div>
      )}
    </div>
  )
}
