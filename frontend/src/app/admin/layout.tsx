"use client"

import Image from "next/image"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { ThemeToggle } from "@/components/ui/ThemeToggle"
import { ToastProvider } from "@/components/ui/Toast"
import { AdminConnectionBanner } from "@/components/admin/AdminConnectionBanner"
import { AdminAuthGate } from "@/components/admin/AdminAuthGate"
import { AdminDataProvider } from "@/lib/useAdminData"

const TABS = [
  { href: "/admin", label: "Review Dokumen" },
  { href: "/admin/monitoring", label: "Monitoring" },
  { href: "/admin/knowledge-graph", label: "Knowledge Graph" },
  { href: "/admin/evaluation", label: "Evaluation" },
]

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()

  return (
    <AdminAuthGate>
      <ToastProvider>
        <AdminDataProvider>
          <main className="min-h-screen bg-background text-ink transition-colors duration-300">
            <header className="flex items-center justify-between border-b border-hairline px-6 py-5">
              <div className="flex items-center gap-4">
                <Image src="/logo.png" alt="Logo" width={48} height={38} className="h-auto w-12 shrink-0" />
                <div>
                  <p className="font-display text-xl font-extrabold leading-tight tracking-tight text-ink">
                    Panel Admin
                  </p>
                  <p className="text-xs text-ink-muted">Campus Virtual Assistant — Poltekkes Kemenkes Yogyakarta</p>
                </div>
              </div>
              <ThemeToggle />
            </header>

            <nav className="flex gap-1 border-b border-hairline px-6">
              {TABS.map((tab) => {
                const isActive =
                  pathname === tab.href || (tab.href !== "/admin" && pathname.startsWith(`${tab.href}/`))
                return (
                  <Link
                    key={tab.href}
                    href={tab.href}
                    className={`border-b-2 px-3 py-3 text-sm font-medium transition-colors duration-300 ${
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

            <AdminConnectionBanner />

            <div className="mx-auto max-w-6xl px-6 py-6">{children}</div>
          </main>
        </AdminDataProvider>
      </ToastProvider>
    </AdminAuthGate>
  )
}
