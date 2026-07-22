"use client"

import { useEffect, useState } from "react"
import { ApiClient } from "@/lib/apiClient"

export function useSession() {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    // The chat_session_id cookie is HttpOnly (unreadable from document.cookie), so
    // always call /sessions/init — the backend reuses the cookie's session when it
    // still exists, so this is an idempotent "ensure session" rather than a reset.
    ApiClient.initSession()
      .then((response) => {
        setSessionId(response.session_id)
        setError(null)
      })
      .catch((err) => {
        setError(err.message)
      })
      .finally(() => setLoading(false))
  }, [])

  return { sessionId, loading, error }
}
