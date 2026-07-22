"use client"

import { useEffect, useRef } from "react"
import type { Message } from "@/types/chat"
import { AnswerMarkdown } from "./AnswerMarkdown"
import { SourceList } from "./SourceList"
import { TypingIndicator } from "./TypingIndicator"
import { ErrorState } from "./ErrorState"

// Shown once at the start of a chat session, before the first user message.
const GREETING_TEXT =
  "Halo! Saya Asisten Virtual Poltekkes Kemenkes Yogyakarta. Saya siap membantu Anda " +
  "dengan informasi resmi seputar penerimaan mahasiswa baru (SPMB), layanan akademik, " +
  "dan administrasi kampus. Silakan ketik pertanyaan Anda, atau pilih salah satu " +
  "pertanyaan berikut:"

const QUICK_QUESTIONS = [
  "Apa saja persyaratan pendaftaran SPMB?",
  "Berapa biaya pendaftaran SPMB?",
  "Kapan jadwal pendaftaran SPMB?",
  "Bagaimana alur pendaftaran SPMB jalur mandiri?",
]

function GreetingIntro({ onQuickQuestion }: { onQuickQuestion: (question: string) => void }) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex justify-start">
        <div className="max-w-[92%] rounded-2xl rounded-bl-sm border border-hairline bg-surface-elevated px-4 py-3 text-ink transition-colors duration-300">
          <p className="text-sm leading-relaxed">{GREETING_TEXT}</p>
        </div>
      </div>
      <div className="flex flex-wrap gap-2 pl-1">
        {QUICK_QUESTIONS.map((question) => (
          <button
            key={question}
            type="button"
            onClick={() => onQuickQuestion(question)}
            className="rounded-full border border-primary/40 bg-primary/5 px-3 py-1.5 text-left text-xs font-medium text-primary transition-all duration-200 hover:bg-primary/15 active:scale-95"
          >
            {question}
          </button>
        ))}
      </div>
    </div>
  )
}

interface MessageListProps {
  messages: Message[]
  sending: boolean
  error: string | null
  /** Sends a preset question when a quick-question chip is tapped on the greeting screen. */
  onQuickQuestion: (question: string) => void
}

export function MessageList({ messages, sending, error, onQuickQuestion }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, sending])

  return (
    <div className="flex-1 space-y-4 overflow-y-auto p-4">
      {messages.length === 0 && !sending && <GreetingIntro onQuickQuestion={onQuickQuestion} />}

      {messages.map((message, idx) => (
        <div
          key={idx}
          className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
        >
          <div
            className={`rounded-2xl px-4 py-3 transition-colors duration-300 ${
              message.role === "user"
                ? "max-w-[85%] rounded-br-sm bg-primary text-white"
                : "max-w-[92%] rounded-bl-sm border border-hairline bg-surface-elevated text-ink"
            }`}
          >
            {message.role === "assistant" ? (
              <AnswerMarkdown content={message.content} />
            ) : (
              <p className="text-sm leading-relaxed">{message.content}</p>
            )}
            <p
              className={`mt-1 text-xs ${
                message.role === "user" ? "text-white/70" : "text-ink-muted"
              }`}
            >
              {message.timestamp.toLocaleTimeString("id-ID", {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </p>
            {message.role === "assistant" && message.sources && (
              <SourceList sources={message.sources} attachments={message.attachments} />
            )}
          </div>
        </div>
      ))}

      {sending && <TypingIndicator />}
      {error && <ErrorState message={error} />}

      <div ref={bottomRef} />
    </div>
  )
}
