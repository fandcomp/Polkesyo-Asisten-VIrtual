"use client"

import Image from "next/image"
import type { Message } from "@/types/chat"
import { ThemeToggle } from "@/components/ui/ThemeToggle"
import { MessageList } from "./MessageList"
import { MessageInput } from "./MessageInput"
import { ChatBackground } from "./ChatBackground"
import { ResizeToggleButton } from "./ResizeToggleButton"

interface ChatUIProps {
  messages: Message[]
  input: string
  onInputChange: (value: string) => void
  onSubmit: (e: React.FormEvent) => void
  /** Sends a preset question directly — used by the greeting screen's quick-question chips. */
  onQuickQuestion: (question: string) => void
  sending: boolean
  error: string | null
  onClose?: () => void
  isExpanded: boolean
  onToggleExpand: () => void
}

export function ChatUI({
  messages,
  input,
  onInputChange,
  onSubmit,
  onQuickQuestion,
  sending,
  error,
  onClose,
  isExpanded,
  onToggleExpand,
}: ChatUIProps) {
  return (
    <div className="relative flex h-full flex-col overflow-hidden transition-colors duration-300">
      <ChatBackground isExpanded={isExpanded} />
      <div
        className="relative z-10 flex flex-col gap-2 border-b border-[rgba(255,255,255,0.22)] px-5 py-4 backdrop-blur-[3px] transition-colors duration-300"
        style={{
          backgroundColor: "rgba(0,174,179,0.30)",
          boxShadow: "0 4px 20px rgba(0,0,0,0.10)",
        }}
      >
        <div className="flex items-center justify-between">
          <Image
            src="/logo.png"
            alt="Logo Campus Virtual Assistant"
            width={56}
            height={45}
            className="h-auto w-14 shrink-0"
          />
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <ResizeToggleButton isExpanded={isExpanded} onToggle={onToggleExpand} variant="dark" />
            {onClose && (
              <button
                type="button"
                onClick={onClose}
                aria-label="Tutup asisten"
                className="flex h-8 w-8 items-center justify-center rounded-full text-white/80 transition-all duration-200 hover:bg-white/15 hover:text-white active:scale-90"
              >
                <CloseIcon className="h-4 w-4" />
              </button>
            )}
          </div>
        </div>
        <div>
          <h1 className="font-display text-2xl font-extrabold leading-tight tracking-tight text-white [text-shadow:0_1px_3px_rgba(0,0,0,0.35)]">
            Campus Virtual Assistant
          </h1>
          <p className="text-xs text-white/90 [text-shadow:0_1px_2px_rgba(0,0,0,0.35)]">
            Poltekkes Kemenkes Yogyakarta
          </p>
        </div>
      </div>

      <div className="relative z-10 flex flex-1 flex-col overflow-hidden">
        <MessageList
          messages={messages}
          sending={sending}
          error={error}
          onQuickQuestion={onQuickQuestion}
        />
        <MessageInput value={input} onChange={onInputChange} onSubmit={onSubmit} disabled={sending} />
      </div>
    </div>
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
