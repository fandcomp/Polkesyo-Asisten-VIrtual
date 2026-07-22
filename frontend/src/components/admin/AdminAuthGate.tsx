"use client"

import { useEffect, useState } from "react"
import { ApiClient } from "@/lib/apiClient"
import { Button } from "@/components/ui/Button"

export function AdminAuthGate({ children }: { children: React.ReactNode }) {
  const [authed, setAuthed] = useState<boolean | null>(null)
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    setAuthed(ApiClient.hasAdminCredentials())
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const ok = await ApiClient.verifyAdminCredentials(username, password)
      if (!ok) {
        setError("Username atau password admin salah.")
        return
      }
      ApiClient.setAdminCredentials(username, password)
      setAuthed(true)
    } catch {
      setError("Tidak dapat terhubung ke server. Periksa koneksi dan coba lagi.")
    } finally {
      setSubmitting(false)
    }
  }

  if (authed === null) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background text-sm text-ink-muted transition-colors duration-300">
        Memuat...
      </div>
    )
  }

  if (!authed) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-4 transition-colors duration-300">
        <form
          onSubmit={handleSubmit}
          className="w-full max-w-sm rounded-2xl border border-hairline bg-background p-6 shadow-premium"
        >
          <h1 className="font-display text-xl font-extrabold text-ink">Masuk Admin</h1>
          <p className="mt-1 text-sm text-ink-muted">
            Panel Admin Campus Virtual Assistant
          </p>

          <label className="mt-5 block text-sm font-medium text-ink">
            Username
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              required
              className="mt-1 w-full rounded-lg border border-hairline bg-background px-3 py-2 text-sm text-ink outline-none focus:border-primary"
            />
          </label>

          <label className="mt-4 block text-sm font-medium text-ink">
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
              className="mt-1 w-full rounded-lg border border-hairline bg-background px-3 py-2 text-sm text-ink outline-none focus:border-primary"
            />
          </label>

          {error && <p className="mt-3 text-sm text-danger">{error}</p>}

          <Button type="submit" disabled={submitting} className="mt-5 w-full">
            {submitting ? "Memeriksa..." : "Masuk"}
          </Button>
        </form>
      </div>
    )
  }

  return <>{children}</>
}
