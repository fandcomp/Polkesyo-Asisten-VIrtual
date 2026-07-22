"use client"

import { useState } from "react"
import Image from "next/image"
import { AssistantWidget } from "@/components/assistant/AssistantWidget"
import { BackgroundAssetPreloader } from "@/components/assistant/BackgroundAssetPreloader"
import { FloatingChatButton } from "@/components/assistant/FloatingChatButton"
import { ThemeToggle } from "@/components/ui/ThemeToggle"

export default function Home() {
  const [isAssistantOpen, setIsAssistantOpen] = useState(false)

  return (
    <main className="min-h-screen bg-background text-ink transition-colors duration-300">
      <header className="flex flex-col gap-2 border-b border-hairline px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-4">
          <Image src="/logo.png" alt="Logo" width={52} height={41} className="h-auto w-[52px] shrink-0" />
          <span className="font-display text-2xl font-extrabold leading-tight tracking-tight text-ink sm:text-3xl">
            Poltekkes Kemenkes Yogyakarta
          </span>
        </div>
        <ThemeToggle />
      </header>

      <section className="mx-auto max-w-2xl px-6 py-16 text-center">
        <h1 className="text-3xl font-bold text-ink">Portal Informasi SPMB</h1>
        <p className="mt-3 text-ink-muted">
          Informasi resmi seputar penerimaan mahasiswa baru, akademik, dan layanan kampus
          Poltekkes Kemenkes Yogyakarta. Gunakan Asisten Kampus di pojok kanan bawah untuk
          bertanya langsung.
        </p>
      </section>

      <BackgroundAssetPreloader />

      {!isAssistantOpen && <FloatingChatButton onClick={() => setIsAssistantOpen(true)} />}

      {isAssistantOpen && <AssistantWidget onClose={() => setIsAssistantOpen(false)} />}
    </main>
  )
}
