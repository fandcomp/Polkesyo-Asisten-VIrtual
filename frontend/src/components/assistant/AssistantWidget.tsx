"use client"

import { useEffect, useState } from "react"
import { useSession } from "@/lib/useSession"
import { ApiClient, ChatApiError } from "@/lib/apiClient"
import type { Message } from "@/types/chat"
import { ConsentBanner } from "./ConsentBanner"
import { WelcomeScreen } from "./WelcomeScreen"
import { ChatUI } from "./ChatUI"

type AssistantView = "welcome" | "chat"

interface AssistantWidgetProps {
  onClose?: () => void
}

const EXPAND_STORAGE_KEY = "chatbot-expanded"

// Mobile segment (unprefixed) is identical in both — fixed inset-0, no radius, no translate —
// so the widget never visually changes on mobile regardless of isExpanded (kept intentionally
// unchanged from the previous fullscreen-on-mobile behavior). Both strings declare
// translate-x-0 translate-y-0 unprefixed so the `transform` property exists in both states and
// interpolates smoothly at sm:-translate-x-1/2 sm:-translate-y-1/2 instead of jumping.
const SHELL_SMALL_CLASSES =
  "fixed inset-0 z-50 overflow-hidden transition-all duration-300 ease-in-out translate-x-0 translate-y-0 " +
  "sm:inset-auto sm:bottom-6 sm:right-6 sm:top-auto sm:left-auto sm:h-[600px] sm:w-[380px] sm:rounded-3xl sm:border sm:border-hairline sm:shadow-premium " +
  "lg:h-[640px] lg:w-[400px]"

const SHELL_EXPANDED_CLASSES =
  "fixed inset-0 z-50 overflow-hidden transition-all duration-300 ease-in-out translate-x-0 translate-y-0 " +
  "sm:inset-auto sm:top-1/2 sm:left-1/2 sm:right-auto sm:bottom-auto sm:-translate-x-1/2 sm:-translate-y-1/2 sm:h-[85vh] sm:w-[90vw] sm:rounded-2xl sm:border sm:border-hairline sm:shadow-premium " +
  "lg:h-[85vh] lg:max-h-[850px] lg:w-[75vw] lg:max-w-[1150px]"

const OVERLAY_CLASSES = "fixed inset-0 z-40 bg-black/60"

export function AssistantWidget({ onClose }: AssistantWidgetProps) {
  const { sessionId, loading: sessionLoading } = useSession()
  const [view, setView] = useState<AssistantView>("welcome")
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isExpanded, setIsExpanded] = useState(false)

  useEffect(() => {
    const stored = window.localStorage.getItem(EXPAND_STORAGE_KEY)
    if (stored === "true") setIsExpanded(true)
  }, [])

  useEffect(() => {
    window.localStorage.setItem(EXPAND_STORAGE_KEY, String(isExpanded))
  }, [isExpanded])

  const handleToggleExpand = () => setIsExpanded((prev) => !prev)

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault()
    await sendText(input)
  }

  // Shared by the input form and the quick-question chips on the greeting screen.
  const sendText = async (messageText: string) => {
    if (!messageText.trim() || sending) return

    const userMessage: Message = {
      role: "user",
      content: messageText,
      timestamp: new Date(),
    }
    setMessages((prev) => [...prev, userMessage])
    setInput("")
    setSending(true)
    setError(null)

    const request = {
      message: messageText,
      metadata: {
        source_page: "assistant-widget",
      },
    }

    try {
      let response
      try {
        response = await ApiClient.sendMessage(request)
      } catch (err) {
        // Backend no longer knows this session (e.g. after a backend redeploy or a
        // stale cookie) — recover in place instead of telling the user to reload.
        if (err instanceof ChatApiError && err.errorType === "session_not_found") {
          response = await ApiClient.recoverSessionAndRetry(request)
        } else {
          throw err
        }
      }

      const assistantMessage: Message = {
        role: "assistant",
        content: response.answer,
        timestamp: new Date(),
        sources: response.sources,
        attachments: response.attachments,
      }
      setMessages((prev) => [...prev, assistantMessage])
    } catch (err) {
      // ChatApiError already carries a user-displayable Indonesian message (apiClient maps
      // timeout/network/server bodies). Restore the question so the user can retry without
      // retyping — no automatic resend: the request may have been processed server-side.
      setError(
        err instanceof Error
          ? err.message
          : "Terjadi gangguan pada layanan. Silakan coba lagi beberapa saat.",
      )
      setMessages((prev) => prev.filter((m) => m !== userMessage))
      setInput(messageText)
    } finally {
      setSending(false)
    }
  }

  let content: React.ReactNode
  if (sessionLoading) {
    content = (
      <div className="flex h-full items-center justify-center bg-background p-4 text-center text-sm text-ink-muted transition-colors duration-300">
        Menyiapkan sesi...
      </div>
    )
  } else if (!sessionId) {
    content = (
      <div className="flex h-full items-center justify-center bg-background p-4 text-center text-sm text-danger transition-colors duration-300">
        Gagal menginisialisasi sesi. Silakan muat ulang halaman.
      </div>
    )
  } else {
    content = (
      <div className="relative h-full overflow-hidden">
        {view === "welcome" ? (
          <WelcomeScreen
            onStart={() => setView("chat")}
            onClose={onClose}
            isExpanded={isExpanded}
            onToggleExpand={handleToggleExpand}
          />
        ) : (
          <ChatUI
            messages={messages}
            input={input}
            onInputChange={setInput}
            onSubmit={handleSend}
            onQuickQuestion={(question) => void sendText(question)}
            sending={sending}
            error={error}
            onClose={onClose}
            isExpanded={isExpanded}
            onToggleExpand={handleToggleExpand}
          />
        )}
        <ConsentBanner />
      </div>
    )
  }

  return (
    <>
      {isExpanded && (
        <div className={OVERLAY_CLASSES} onClick={() => setIsExpanded(false)} aria-hidden="true" />
      )}
      <div className={isExpanded ? SHELL_EXPANDED_CLASSES : SHELL_SMALL_CLASSES}>{content}</div>
    </>
  )
}
