"use client"

import { useCallback, useEffect, useState } from "react"
import { ApiClient, type DocumentSourceResponse } from "@/lib/apiClient"
import { useAdminData } from "@/lib/useAdminData"

type PanelState =
  | { phase: "loading" }
  | { phase: "error"; message: string }
  | { phase: "loaded"; sources: DocumentSourceResponse[] }

// Raw source_type values match DocumentSource.source_type (backend/app/db/models.py) —
// readable here as e.g. "Sinkronisasi Resmi" instead of the technical "official_sync" admins
// would otherwise see verbatim. Falls back to the raw value for any type not yet mapped.
const SOURCE_TYPE_LABEL: Record<string, string> = {
  manual_upload: "Unggah Manual",
  official_sync: "Sinkronisasi Resmi",
}

function sourceTypeLabel(type: string): string {
  return SOURCE_TYPE_LABEL[type] ?? type
}

export function DocumentSourceMonitorPanel() {
  const { mode } = useAdminData()
  const [state, setState] = useState<PanelState>({ phase: "loading" })

  const refresh = useCallback(async () => {
    setState({ phase: "loading" })
    try {
      const sources = await ApiClient.listDocumentSources()
      setState({ phase: "loaded", sources })
    } catch (err: unknown) {
      setState({ phase: "error", message: err instanceof Error ? err.message : "Gagal memuat sumber dokumen" })
    }
  }, [])

  useEffect(() => {
    if (mode === "live") void refresh()
  }, [mode, refresh])

  if (mode !== "live") {
    return (
      <div className="rounded-2xl border border-hairline bg-surface p-4 shadow-premium">
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">Sumber Dokumen</p>
        <p className="mt-2 text-sm text-ink-muted">Hanya tersedia dalam mode live (backend terhubung).</p>
      </div>
    )
  }

  return (
    <div className="rounded-2xl border border-hairline bg-surface p-4 shadow-premium transition-colors duration-300">
      <div className="mb-3 flex items-center justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">Sumber Dokumen</p>
        <div className="flex items-center gap-2">
          <p className="text-xs text-ink-muted">Sumber: GET /admin/documents/sources</p>
          <button
            type="button"
            onClick={() => void refresh()}
            disabled={state.phase === "loading"}
            aria-label="Muat ulang sumber dokumen"
            className="rounded-lg border border-hairline px-2 py-1 text-xs text-ink-muted transition-colors duration-300 hover:bg-surface-elevated hover:text-ink disabled:opacity-50"
          >
            Muat Ulang
          </button>
        </div>
      </div>

      {state.phase === "loading" && <p className="text-sm text-ink-muted">Memuat…</p>}
      {state.phase === "error" && <p className="text-sm text-danger">{state.message}</p>}
      {state.phase === "loaded" && state.sources.length === 0 && (
        <p className="text-sm text-ink-muted">Belum ada sumber dokumen terdaftar.</p>
      )}
      {state.phase === "loaded" && state.sources.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-left text-sm">
            <thead>
              <tr className="text-xs uppercase tracking-wide text-ink-muted">
                <th className="pb-2 pr-3 font-medium">Nama</th>
                <th className="pb-2 pr-3 font-medium">Tipe</th>
                <th className="pb-2 pr-3 font-medium">Status</th>
                <th className="pb-2 font-medium">Terakhir Diperiksa</th>
              </tr>
            </thead>
            <tbody>
              {state.sources.map((source) => (
                <tr key={source.id} className="border-t border-hairline">
                  <td className="py-2 pr-3">
                    <a
                      href={source.source_url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="text-ink underline decoration-hairline underline-offset-2 hover:text-ink-muted"
                    >
                      {source.source_name}
                    </a>
                  </td>
                  <td className="py-2 pr-3 text-ink-muted">{sourceTypeLabel(source.source_type)}</td>
                  <td className="py-2 pr-3">
                    <span
                      className={
                        source.is_active
                          ? "rounded-full border border-success/40 bg-success/10 px-2 py-0.5 text-xs text-success"
                          : "rounded-full border border-hairline bg-surface-elevated px-2 py-0.5 text-xs text-ink-muted"
                      }
                    >
                      {source.is_active ? "Aktif" : "Nonaktif"}
                    </span>
                  </td>
                  <td className="py-2 text-ink-muted">
                    {source.last_checked_at ? new Date(source.last_checked_at).toLocaleString("id-ID") : "Belum pernah"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
