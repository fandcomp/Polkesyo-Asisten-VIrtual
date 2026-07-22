"use client"

import { useCallback, useEffect, useState } from "react"
import { ApiClient } from "@/lib/apiClient"

type ServiceStatus = "ok" | "error" | "unknown"

const SERVICES: { key: string; label: string }[] = [
  { key: "postgres", label: "PostgreSQL" },
  { key: "redis", label: "Redis" },
  { key: "chroma", label: "Chroma (Vector RAG)" },
  { key: "neo4j", label: "Neo4j (GraphRAG)" },
]

const STATUS_STYLE: Record<ServiceStatus, string> = {
  ok: "border-success/40 bg-success/10 text-success",
  error: "border-danger-border bg-danger-bg text-danger",
  unknown: "border-hairline bg-surface-elevated text-ink-muted",
}

const STATUS_LABEL: Record<ServiceStatus, string> = {
  ok: "Aktif",
  error: "Bermasalah",
  unknown: "Belum Terhubung",
}

type PanelState =
  | { phase: "loading" }
  | { phase: "unreachable" }
  | { phase: "loaded"; services: Record<string, ServiceStatus> }

export function SystemHealthPanel() {
  const [state, setState] = useState<PanelState>({ phase: "loading" })

  const refresh = useCallback(async () => {
    setState({ phase: "loading" })
    try {
      const health = await ApiClient.getHealth()
      const services: Record<string, ServiceStatus> = {}
      for (const { key } of SERVICES) {
        services[key] = health.services[key] === "ok" ? "ok" : "error"
      }
      setState({ phase: "loaded", services })
    } catch {
      setState({ phase: "unreachable" })
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const sourceLabel =
    state.phase === "loading"
      ? "Sumber: GET /health (memuat…)"
      : state.phase === "unreachable"
        ? "Sumber: GET /health (backend tidak terjangkau)"
        : "Sumber: GET /health"

  return (
    <div className="rounded-2xl border border-hairline bg-surface p-4 shadow-premium transition-colors duration-300">
      <div className="mb-3 flex items-center justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">Status Layanan</p>
        <div className="flex items-center gap-2">
          <p className="text-xs text-ink-muted">{sourceLabel}</p>
          <button
            type="button"
            onClick={() => void refresh()}
            disabled={state.phase === "loading"}
            aria-label="Muat ulang status layanan"
            className="rounded-lg border border-hairline px-2 py-1 text-xs text-ink-muted transition-colors duration-300 hover:bg-surface-elevated hover:text-ink disabled:opacity-50"
          >
            Muat Ulang
          </button>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {SERVICES.map((service) => {
          const status: ServiceStatus =
            state.phase === "loaded" ? state.services[service.key] : "unknown"
          return (
            <div
              key={service.key}
              className={`flex flex-col gap-1 rounded-xl border px-3 py-2 transition-colors duration-300 ${STATUS_STYLE[status]}`}
            >
              <span className="text-xs font-medium">{service.label}</span>
              <span className="text-xs opacity-80">
                {state.phase === "loading" ? "Memuat…" : STATUS_LABEL[status]}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
