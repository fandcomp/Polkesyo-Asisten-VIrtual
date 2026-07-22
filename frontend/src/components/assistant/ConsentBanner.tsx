"use client"

import { ConsentValue, useConsent } from "@/lib/useConsent"
import { Button } from "@/components/ui/Button"

export function ConsentBanner() {
  const { showBanner, handleConsent } = useConsent()

  if (!showBanner) return null

  return (
    <div className="absolute bottom-0 left-0 right-0 z-10 border-t border-hairline bg-surface p-4 shadow-premium transition-colors duration-300">
      <div className="mx-auto max-w-4xl">
        <p className="mb-4 text-sm text-ink">
          Kami menggunakan cookie untuk meningkatkan pengalaman Anda. Anda dapat memilih hanya cookie esensial atau mengizinkan riwayat dan analitik untuk pengalaman yang lebih baik.
        </p>
        <div className="flex gap-3">
          <Button variant="secondary" onClick={() => handleConsent("essential_only" as ConsentValue)}>
            Hanya Esensial
          </Button>
          <Button variant="primary" onClick={() => handleConsent("history_and_analytics" as ConsentValue)}>
            Setujui Semua
          </Button>
        </div>
      </div>
    </div>
  )
}
