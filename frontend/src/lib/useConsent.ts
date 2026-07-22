"use client"

import { useEffect, useState } from "react"
import { ApiClient } from "@/lib/apiClient"

export type ConsentValue = "essential_only" | "history_and_analytics"

export function useConsent() {
  const [consent, setConsent] = useState<ConsentValue | null>(null)
  const [showBanner, setShowBanner] = useState(false)

  useEffect(() => {
    // Check if consent cookie exists
    const match = document.cookie.match(/chat_consent=([^;]+)/)
    if (match) {
      setConsent(match[1] as ConsentValue)
      setShowBanner(false)
    } else {
      setShowBanner(true)
    }
  }, [])

  const handleConsent = async (value: ConsentValue) => {
    try {
      await ApiClient.setConsent(value)
      setConsent(value)
      setShowBanner(false)
      // Set consent cookie for client-side tracking
      document.cookie = `chat_consent=${value}; Path=/; Max-Age=2592000; SameSite=Lax`
    } catch (error) {
      console.error("Failed to set consent:", error)
    }
  }

  return { consent, showBanner, handleConsent }
}
