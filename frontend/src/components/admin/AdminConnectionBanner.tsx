"use client"

import { useAdminData } from "@/lib/useAdminData"

/**
 * Shows the admin panel's backend connection state: demo-mode notice when the
 * backend is unreachable, and the latest API error when a live call fails.
 */
export function AdminConnectionBanner() {
  const { mode, apiError, retryConnection } = useAdminData()

  if (mode === "live" && !apiError) return null

  if (mode === "connecting") {
    return (
      <div className="border-b border-hairline bg-surface-elevated px-6 py-2 text-xs text-ink-muted">
        Menghubungkan ke backend…
      </div>
    )
  }

  if (mode === "demo") {
    return (
      <div className="flex items-center gap-3 border-b border-warning/40 bg-warning/10 px-6 py-2 text-xs text-warning">
        <span>
          Mode demo — backend tidak terjangkau, menampilkan data contoh. Perubahan tidak tersimpan.
        </span>
        <button
          type="button"
          onClick={retryConnection}
          className="shrink-0 rounded-md border border-warning/40 px-2 py-0.5 font-medium text-warning transition-colors hover:bg-warning/20 active:scale-95"
        >
          Coba lagi
        </button>
      </div>
    )
  }

  return (
    <div className="border-b border-danger-border bg-danger-bg px-6 py-2 text-xs text-danger">
      Gagal memproses permintaan: {apiError}
    </div>
  )
}
