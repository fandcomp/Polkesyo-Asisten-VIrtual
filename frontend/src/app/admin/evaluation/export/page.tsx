"use client"

import { useState } from "react"
import { Button } from "@/components/ui/Button"
import { ApiClient } from "@/lib/apiClient"
import { useToast } from "@/components/ui/Toast"

const EXPORTS: Array<{ kind: Parameters<typeof ApiClient.downloadEvaluationExport>[0]; label: string; filename: string }> = [
  { kind: "chat-logs", label: "Log Teknis Chat", filename: "chat_evaluation_logs.csv" },
  { kind: "retrieval", label: "Log Retrieval", filename: "retrieval_evaluation_logs.csv" },
  { kind: "citations", label: "Log Sitasi", filename: "citation_evaluation_logs.csv" },
  { kind: "acif", label: "Trace ACIF", filename: "acif_trace_logs.csv" },
  { kind: "asq", label: "Respon ASQ", filename: "asq_responses.csv" },
  { kind: "sus", label: "Respon SUS", filename: "sus_responses.csv" },
  { kind: "combined-report", label: "Laporan Gabungan (Combined Report)", filename: "combined_report.csv" },
]

export default function ExportCenterPage() {
  const { showToast } = useToast()
  const [downloading, setDownloading] = useState<string | null>(null)

  const download = async (kind: (typeof EXPORTS)[number]["kind"], filename: string) => {
    setDownloading(kind)
    try {
      await ApiClient.downloadEvaluationExport(kind, {}, filename)
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Gagal mengekspor CSV.", "error")
    } finally {
      setDownloading(null)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-ink-muted">
        Unduh data evaluasi sebagai CSV untuk pelaporan akademik. Semua ekspor dibatasi oleh
        EVALUATION_EXPORT_MAX_ROWS dan tidak pernah menyertakan prompt mentah atau kredensial.
      </p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {EXPORTS.map((exp) => (
          <div
            key={exp.kind}
            className="flex items-center justify-between rounded-2xl border border-hairline bg-surface p-4 shadow-premium"
          >
            <span className="text-sm font-medium text-ink">{exp.label}</span>
            <Button
              variant="secondary"
              className="px-3 py-1.5 text-xs"
              disabled={downloading === exp.kind}
              onClick={() => void download(exp.kind, exp.filename)}
            >
              {downloading === exp.kind ? "Mengunduh..." : "Ekspor CSV"}
            </Button>
          </div>
        ))}
      </div>
    </div>
  )
}
