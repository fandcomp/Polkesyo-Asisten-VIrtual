"use client"

import { useEffect, useRef, useState } from "react"
import { AnswerMarkdown } from "@/components/assistant/AnswerMarkdown"
import { TypingIndicator } from "@/components/assistant/TypingIndicator"
import { Button } from "@/components/ui/Button"
import { ApiClient, type EvaluationScenarioResponse } from "@/lib/apiClient"

type Step = "code" | "instructions" | "scenario" | "asq" | "sus" | "done" | "loading" | "error"

interface ChatMessage {
  role: "user" | "assistant"
  content: string
  traceId?: string
}

const ASQ_QUESTIONS = [
  "Secara keseluruhan, saya puas dengan kemudahan dalam menyelesaikan tugas ini menggunakan asisten virtual.",
  "Secara keseluruhan, saya puas dengan waktu yang dibutuhkan untuk menyelesaikan tugas ini.",
  "Secara keseluruhan, saya puas dengan informasi pendukung, petunjuk, atau pesan yang diberikan asisten virtual selama menyelesaikan tugas ini.",
]

const SUS_QUESTIONS = [
  "Saya merasa ingin sering menggunakan asisten virtual ini.",
  "Saya merasa asisten virtual ini terlalu rumit digunakan.",
  "Saya merasa asisten virtual ini mudah digunakan.",
  "Saya membutuhkan bantuan orang teknis untuk dapat menggunakan asisten virtual ini.",
  "Saya merasa fitur-fitur dalam asisten virtual ini berjalan dengan baik.",
  "Saya merasa terdapat terlalu banyak ketidakkonsistenan dalam asisten virtual ini.",
  "Saya membayangkan sebagian besar pengguna akan cepat belajar menggunakan asisten virtual ini.",
  "Saya merasa asisten virtual ini sulit digunakan.",
  "Saya merasa percaya diri saat menggunakan asisten virtual ini.",
  "Saya perlu mempelajari banyak hal terlebih dahulu sebelum dapat menggunakan asisten virtual ini.",
]

const SCALE_7 = [1, 2, 3, 4, 5, 6, 7]
const SCALE_5 = [1, 2, 3, 4, 5]

export default function EvaluationPage() {
  const [step, setStep] = useState<Step>("code")
  const [participantCode, setParticipantCode] = useState("")
  const [scenarios, setScenarios] = useState<EvaluationScenarioResponse[]>([])
  const [scenarioIndex, setScenarioIndex] = useState(0)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState("")
  const [sending, setSending] = useState(false)
  const lastTraceId = useRef<string | undefined>(undefined)

  const [asqAnswers, setAsqAnswers] = useState<[number, number, number]>([4, 4, 4])
  const [susAnswers, setSusAnswers] = useState<number[]>(Array(10).fill(3))

  const currentScenario = scenarios[scenarioIndex]

  const start = async () => {
    if (!participantCode.trim()) {
      setError("Kode partisipan wajib diisi.")
      return
    }
    setStep("loading")
    setError(null)
    try {
      const [session] = await Promise.all([ApiClient.initSession()])
      await ApiClient.setConsent("history_and_analytics")
      setSessionId(session.session_id)

      const loadedScenarios = await ApiClient.listEvaluationScenarios()
      if (loadedScenarios.length === 0) {
        setError("Belum ada skenario evaluasi yang tersedia. Hubungi admin.")
        setStep("error")
        return
      }
      setScenarios(loadedScenarios)
      setScenarioIndex(0)
      setStep("instructions")
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Gagal memulai sesi evaluasi.")
      setStep("error")
    }
  }

  const beginScenario = () => {
    setMessages([])
    setStep("scenario")
  }

  const sendMessage = async () => {
    if (!input.trim() || !currentScenario) return
    const userMessage = input.trim()
    setMessages((prev) => [...prev, { role: "user", content: userMessage }])
    setInput("")
    setSending(true)
    try {
      const response = await ApiClient.sendMessage({
        message: userMessage,
        evaluation_mode: true,
        participant_code: participantCode,
        scenario_code: currentScenario.code,
      })
      lastTraceId.current = response.trace_id
      setMessages((prev) => [...prev, { role: "assistant", content: response.answer, traceId: response.trace_id }])
    } catch (e: unknown) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: e instanceof Error ? e.message : "Terjadi kesalahan." },
      ])
    } finally {
      setSending(false)
    }
  }

  const finishScenario = () => {
    setAsqAnswers([4, 4, 4])
    setStep("asq")
  }

  const submitAsq = async () => {
    if (!currentScenario) return
    setStep("loading")
    try {
      await ApiClient.submitAsq({
        participant_code: participantCode,
        scenario_code: currentScenario.code,
        session_id: sessionId ?? undefined,
        trace_id: lastTraceId.current,
        asq_1: asqAnswers[0],
        asq_2: asqAnswers[1],
        asq_3: asqAnswers[2],
      })
      if (scenarioIndex + 1 < scenarios.length) {
        setScenarioIndex((i) => i + 1)
        setStep("instructions")
      } else {
        setSusAnswers(Array(10).fill(3))
        setStep("sus")
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Gagal mengirim ASQ.")
      setStep("error")
    }
  }

  const submitSus = async () => {
    setStep("loading")
    try {
      await ApiClient.submitSus({
        participant_code: participantCode,
        session_id: sessionId ?? undefined,
        sus_1: susAnswers[0], sus_2: susAnswers[1], sus_3: susAnswers[2], sus_4: susAnswers[3],
        sus_5: susAnswers[4], sus_6: susAnswers[5], sus_7: susAnswers[6], sus_8: susAnswers[7],
        sus_9: susAnswers[8], sus_10: susAnswers[9],
      })
      setStep("done")
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Gagal mengirim SUS.")
      setStep("error")
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 bg-background px-6 py-10 text-ink">
      <div>
        <p className="font-display text-2xl font-extrabold">Evaluasi Asisten Virtual</p>
        <p className="text-sm text-ink-muted">Poltekkes Kemenkes Yogyakarta — sesi evaluasi partisipan</p>
      </div>

      {step === "code" && (
        <div className="flex flex-col gap-4 rounded-2xl border border-hairline bg-surface p-6 shadow-premium">
          <label className="flex flex-col gap-1 text-sm">
            Kode Partisipan
            <input
              value={participantCode}
              onChange={(e) => setParticipantCode(e.target.value)}
              placeholder="mis. P001"
              className="rounded-xl border border-hairline bg-background px-3 py-2 text-sm"
            />
          </label>
          {error && <p className="text-sm text-danger">{error}</p>}
          <Button variant="primary" onClick={start}>
            Mulai Evaluasi
          </Button>
        </div>
      )}

      {step === "loading" && <p className="text-sm text-ink-muted">Memuat...</p>}

      {step === "error" && (
        <div className="rounded-2xl border border-danger-border bg-danger-bg p-6 text-danger">
          {error ?? "Terjadi kesalahan."}
        </div>
      )}

      {step === "instructions" && currentScenario && (
        <div className="flex flex-col gap-4 rounded-2xl border border-hairline bg-surface p-6 shadow-premium">
          <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
            Skenario {scenarioIndex + 1} dari {scenarios.length}
          </p>
          <p className="font-display text-lg font-bold">{currentScenario.title}</p>
          <p className="text-sm text-ink">{currentScenario.instruction}</p>
          <Button variant="primary" onClick={beginScenario}>
            Mulai Skenario
          </Button>
        </div>
      )}

      {step === "scenario" && currentScenario && (
        <div className="flex flex-col gap-4">
          <div className="rounded-2xl border border-hairline bg-surface-elevated p-4 text-sm text-ink-muted">
            {currentScenario.instruction}
          </div>
          <div className="flex min-h-[300px] flex-col gap-3 rounded-2xl border border-hairline bg-surface p-4 shadow-premium">
            {messages.map((m, i) => (
              <div
                key={i}
                className={`max-w-[85%] rounded-2xl px-4 py-2 text-sm ${
                  m.role === "user" ? "self-end bg-primary text-white" : "self-start bg-surface-elevated text-ink"
                }`}
              >
                {m.role === "assistant" ? <AnswerMarkdown content={m.content} /> : m.content}
              </div>
            ))}
            {sending && <TypingIndicator />}
          </div>
          <div className="flex gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !sending && void sendMessage()}
              placeholder="Ketik pertanyaan Anda..."
              className="flex-1 rounded-xl border border-hairline bg-background px-3 py-2 text-sm"
            />
            <Button variant="secondary" onClick={() => void sendMessage()} disabled={sending}>
              Kirim
            </Button>
          </div>
          <Button variant="primary" onClick={finishScenario} disabled={messages.length === 0}>
            Selesai Skenario
          </Button>
        </div>
      )}

      {step === "asq" && (
        <div className="flex flex-col gap-6 rounded-2xl border border-hairline bg-surface p-6 shadow-premium">
          <p className="font-display text-lg font-bold">Kuesioner Setelah Skenario (ASQ)</p>
          {ASQ_QUESTIONS.map((q, qi) => (
            <div key={qi} className="flex flex-col gap-2">
              <p className="text-sm text-ink">{q}</p>
              <div className="flex gap-2">
                {SCALE_7.map((v) => (
                  <button
                    key={v}
                    onClick={() =>
                      setAsqAnswers((prev) => {
                        const next = [...prev] as [number, number, number]
                        next[qi] = v
                        return next
                      })
                    }
                    className={`h-9 w-9 rounded-full border text-xs font-semibold transition-colors ${
                      asqAnswers[qi] === v
                        ? "border-primary bg-primary text-white"
                        : "border-hairline bg-background text-ink-muted"
                    }`}
                  >
                    {v}
                  </button>
                ))}
              </div>
            </div>
          ))}
          <p className="text-xs text-ink-muted">1 = Sangat tidak setuju, 7 = Sangat setuju</p>
          <Button variant="primary" onClick={() => void submitAsq()}>
            Kirim & Lanjutkan
          </Button>
        </div>
      )}

      {step === "sus" && (
        <div className="flex flex-col gap-6 rounded-2xl border border-hairline bg-surface p-6 shadow-premium">
          <p className="font-display text-lg font-bold">System Usability Scale (SUS)</p>
          {SUS_QUESTIONS.map((q, qi) => (
            <div key={qi} className="flex flex-col gap-2">
              <p className="text-sm text-ink">{qi + 1}. {q}</p>
              <div className="flex gap-2">
                {SCALE_5.map((v) => (
                  <button
                    key={v}
                    onClick={() =>
                      setSusAnswers((prev) => {
                        const next = [...prev]
                        next[qi] = v
                        return next
                      })
                    }
                    className={`h-9 w-9 rounded-full border text-xs font-semibold transition-colors ${
                      susAnswers[qi] === v
                        ? "border-primary bg-primary text-white"
                        : "border-hairline bg-background text-ink-muted"
                    }`}
                  >
                    {v}
                  </button>
                ))}
              </div>
            </div>
          ))}
          <p className="text-xs text-ink-muted">1 = Sangat tidak setuju, 5 = Sangat setuju</p>
          <Button variant="primary" onClick={() => void submitSus()}>
            Kirim
          </Button>
        </div>
      )}

      {step === "done" && (
        <div className="flex flex-col items-center gap-3 rounded-2xl border border-hairline bg-surface p-10 text-center shadow-premium">
          <p className="font-display text-xl font-extrabold">Terima kasih!</p>
          <p className="text-sm text-ink-muted">Evaluasi Anda telah berhasil disimpan.</p>
        </div>
      )}
    </main>
  )
}
