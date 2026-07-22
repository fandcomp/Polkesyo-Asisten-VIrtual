"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { useAdminData } from "@/lib/useAdminData"

// `key` matches the backend's require_evaluation_tab(...) tags in routes_evaluation_admin.py —
// used to hide tabs a restricted (second) admin account can't use. Real enforcement is the
// backend's per-route 403; this filtering is UX only.
const SUB_TABS = [
  { href: "/admin/evaluation", label: "Overview", key: "overview" },
  { href: "/admin/evaluation/technical-logs", label: "Log Teknis", key: "technical_logs" },
  { href: "/admin/evaluation/acif-traces", label: "ACIF Traces", key: "acif_traces" },
  { href: "/admin/evaluation/retrieval", label: "Retrieval", key: "retrieval" },
  { href: "/admin/evaluation/citations", label: "Sitasi", key: "citations" },
  { href: "/admin/evaluation/runs", label: "Evaluation Runs", key: "runs" },
  { href: "/admin/evaluation/compare", label: "Perbandingan ACIF", key: "compare" },
  { href: "/admin/evaluation/dataset", label: "Soal Gold-QA", key: "dataset" },
  { href: "/admin/evaluation/scenarios", label: "Skenario", key: "scenarios" },
  { href: "/admin/evaluation/asq", label: "Hasil ASQ", key: "asq" },
  { href: "/admin/evaluation/sus", label: "Hasil SUS", key: "sus" },
  { href: "/admin/evaluation/export", label: "Export Center", key: "export" },
]

export default function EvaluationLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const { evaluationTabs } = useAdminData()
  const visibleTabs = evaluationTabs
    ? SUB_TABS.filter((tab) => evaluationTabs.includes(tab.key))
    : SUB_TABS

  return (
    <div className="flex flex-col gap-4">
      <div>
        <p className="font-display text-lg font-extrabold text-ink">Evaluation Layer</p>
        <p className="text-xs text-ink-muted">
          Kualitas teknis, keamanan ACIF, dan sitasi untuk setiap interaksi asisten virtual.
        </p>
      </div>

      <nav className="flex gap-1 border-b border-hairline">
        {visibleTabs.map((tab) => {
          const isActive = pathname === tab.href
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={`border-b-2 px-3 py-2 text-sm font-medium transition-colors duration-300 ${
                isActive
                  ? "border-primary text-primary"
                  : "border-transparent text-ink-muted hover:text-ink"
              }`}
            >
              {tab.label}
            </Link>
          )
        })}
      </nav>

      {children}
    </div>
  )
}
