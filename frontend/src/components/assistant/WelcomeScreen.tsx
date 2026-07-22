"use client"

import Image from "next/image"
import { ThemeToggle } from "@/components/ui/ThemeToggle"
import { ResizeToggleButton } from "./ResizeToggleButton"

interface WelcomeScreenProps {
  onStart: () => void
  onClose?: () => void
  isExpanded: boolean
  onToggleExpand: () => void
}

export function WelcomeScreen({ onStart, onClose, isExpanded, onToggleExpand }: WelcomeScreenProps) {
  return (
    <div className="flex h-full w-full flex-col items-center justify-between overflow-hidden bg-background px-6 pb-8 pt-4 text-center transition-colors duration-300">
      <div className="flex w-full items-center justify-end gap-2">
        <ThemeToggle />
        <ResizeToggleButton isExpanded={isExpanded} onToggle={onToggleExpand} variant="light" />
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Tutup asisten"
            className="flex h-8 w-8 items-center justify-center rounded-full text-ink-muted transition-all duration-200 hover:bg-surface-elevated hover:text-ink active:scale-90"
          >
            <CloseIcon className="h-4 w-4" />
          </button>
        )}
      </div>

      <div className="flex w-full max-w-xs flex-1 flex-col items-center justify-center gap-6">
        <Image
          src="/logo.png"
          alt="Logo Campus Virtual Assistant Poltekkes Kemenkes Yogyakarta"
          width={140}
          height={112}
          priority
          className="h-auto w-36"
        />

        <div className="flex flex-col gap-2">
          <h1 className="text-2xl font-bold text-ink">
            Halo! Ada yang bisa kami bantu?
          </h1>
          <p className="text-sm text-ink-muted">
            Tanyakan informasi seputar SPMB, akademik, dan layanan kampus
            Poltekkes Kemenkes Yogyakarta.
          </p>
        </div>

        <div className="flex items-start gap-2 rounded-2xl border border-hairline bg-surface-elevated px-4 py-3 text-left transition-colors duration-300">
          <InfoIcon className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
          <p className="text-xs leading-relaxed text-ink-muted">
            Ini adalah virtual assistant resmi Poltekkes Kemenkes Yogyakarta.
            Jawaban diberikan berdasarkan sumber informasi resmi yang telah
            disetujui.
          </p>
        </div>
      </div>

      <button
        type="button"
        onClick={onStart}
        className="flex w-full max-w-xs items-center justify-between rounded-full border border-gold/60 bg-primary py-2 pl-7 pr-2 shadow-premium transition-transform duration-300 active:scale-[0.98]"
      >
        <span className="text-base font-semibold text-white">Mulai Chat</span>
        <span className="flex h-12 w-12 items-center justify-center rounded-full border-2 border-gold bg-accent">
          <ArrowRightIcon className="h-5 w-5 text-white" />
        </span>
      </button>
    </div>
  )
}

function InfoIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" className={className} aria-hidden="true">
      <path
        fillRule="evenodd"
        d="M10 18a8 8 0 100-16 8 8 0 000 16zm.75-11.5a.75.75 0 11-1.5 0 .75.75 0 011.5 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h.01a1 1 0 100-2H10v-3a1 1 0 00-1-1z"
        clipRule="evenodd"
      />
    </svg>
  )
}

function ArrowRightIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M4 10h12M11 5l5 5-5 5" />
    </svg>
  )
}

function CloseIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M5 5l10 10M15 5L5 15" />
    </svg>
  )
}
