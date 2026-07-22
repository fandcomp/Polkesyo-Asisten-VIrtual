"use client"

/**
 * Warms the browser HTTP cache with the chat-background assets while the host page is idle,
 * so the first time the assistant popup opens its <video> elements read from disk cache
 * instead of fetching ~4.5MB over the network at the exact moment the user is watching.
 *
 * Renders nothing. Mount once on any page that hosts the assistant widget.
 * Paired with the immutable Cache-Control headers on /videos/* and /images/* in
 * next.config.ts, repeat visitors skip the download entirely.
 */

import { useEffect } from "react"
import {
  DARK_TO_LIGHT_SRC,
  EXPANDED_DARK_TO_LIGHT_SRC,
  EXPANDED_LIGHT_TO_DARK_SRC,
  EXPANDED_POSTER_SRC,
  LIGHT_TO_DARK_SRC,
} from "./ChatBackground"

const BACKGROUND_ASSETS: readonly string[] = [
  LIGHT_TO_DARK_SRC,
  DARK_TO_LIGHT_SRC,
  EXPANDED_LIGHT_TO_DARK_SRC,
  EXPANDED_DARK_TO_LIGHT_SRC,
  EXPANDED_POSTER_SRC.light,
  EXPANDED_POSTER_SRC.dark,
]

const IDLE_TIMEOUT_MS = 3000
const FALLBACK_DELAY_MS = 1500

export function BackgroundAssetPreloader() {
  useEffect(() => {
    let cancelled = false

    const warm = () => {
      if (cancelled) return
      for (const url of BACKGROUND_ASSETS) {
        // force-cache: an already-cached copy (from a previous visit) is reused as-is;
        // errors are irrelevant — this is purely opportunistic warming, the ChatBackground
        // fallback chain (poster → gradient) still covers a failed asset.
        fetch(url, { cache: "force-cache" }).catch(() => {})
      }
    }

    // typeof check (not `in` narrowing): requestIdleCallback is still missing in Safari.
    if (typeof window.requestIdleCallback === "function") {
      const id = window.requestIdleCallback(warm, { timeout: IDLE_TIMEOUT_MS })
      return () => {
        cancelled = true
        window.cancelIdleCallback(id)
      }
    }
    const timer = window.setTimeout(warm, FALLBACK_DELAY_MS)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [])

  return null
}
