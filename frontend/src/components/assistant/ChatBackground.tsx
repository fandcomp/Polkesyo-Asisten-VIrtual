"use client"

/**
 * Adaptive light/dark chatbot background, built entirely from two WebM clips — no static image.
 *
 * Expected files (served from `public/`, referenced by absolute path below):
 *   frontend/public/videos/transition-light-to-dark.webm
 *   frontend/public/videos/transition-dark-to-light.webm
 *
 * Frame contract (relied on for seamless swaps, no crossfade needed):
 *   transition-light-to-dark: frame 0 == light static look, last frame == dark static look.
 *   transition-dark-to-light: frame 0 == dark static look, last frame == light static look.
 *
 * Expanded (maximized) mode uses a completely separate pair of assets, following the exact same
 * frame contract and the exact same dual-video-crossfade mechanism (confirmed by sampling frame
 * brightness) — see useThemeTransition.tsx's "expanded" channel:
 *   frontend/public/videos/expanded-dark.webm    frame 0 == light look, last frame == dark look
 *   frontend/public/videos/expanded-light.webm   frame 0 == dark look, last frame == light look
 *   frontend/public/images/expanded-light.png    poster / fallback
 *   frontend/public/images/expanded-dark.png     poster / fallback
 * If the video 404s/errors, falls back to the PNG; if the PNG also 404s/errors, the always-on
 * gradient underlay simply shows through.
 *
 * Instant-readiness design (added after "background takes long to appear" reports):
 *   1. BOTH channel pairs (small + expanded) stay mounted at all times, hidden with CSS
 *      opacity only — never conditionally unmounted by isExpanded. A minimize↔maximize
 *      switch is therefore just an opacity flip on already-decoded, already-seeked video
 *      elements, instead of a fresh mount → network fetch → decode → seek cycle.
 *   2. A flat gradient underlay is ALWAYS painted beneath the videos, so the very first
 *      frame after the popup opens shows a correct-looking backdrop even if the video is
 *      still decoding (previously the gradient only appeared on video *error*).
 *   3. Asset bytes are pre-warmed into the HTTP cache while the host page is idle — see
 *      BackgroundAssetPreloader.tsx — so the first popup open reads from disk cache.
 *   4. Which channel is visible is reported to useThemeTransition (setVisibleChannel) so a
 *      theme toggle animates the channel the user actually sees; the hidden channel snaps
 *      to the settled frame via the provider's settle effect.
 */

import { useEffect, useState } from "react"
import { useThemeTransition } from "@/lib/useThemeTransition"

export const LIGHT_TO_DARK_SRC = "/videos/transition-light-to-dark.webm"
export const DARK_TO_LIGHT_SRC = "/videos/transition-dark-to-light.webm"

// Named by direction (matching the small-mode refs), not by the theme it's used for — the
// "light-to-dark" clip is the file that ends dark (expanded-dark.webm), and vice versa.
export const EXPANDED_LIGHT_TO_DARK_SRC = "/videos/expanded-dark.webm"
export const EXPANDED_DARK_TO_LIGHT_SRC = "/videos/expanded-light.webm"

export const EXPANDED_POSTER_SRC = {
  light: "/images/expanded-light.png",
  dark: "/images/expanded-dark.png",
} as const

interface ChatBackgroundProps {
  isExpanded: boolean
}

function GradientFallback({ theme }: { theme: "light" | "dark" }) {
  return (
    <div
      className={`absolute inset-0 transition-colors duration-300 ${
        theme === "dark"
          ? "bg-gradient-to-b from-[#07110f] to-[#0b2c29]"
          : "bg-gradient-to-b from-white to-primary/15"
      }`}
    />
  )
}

export function ChatBackground({ isExpanded }: ChatBackgroundProps) {
  const {
    theme,
    activeVideo,
    videoError,
    lightToDarkRef,
    darkToLightRef,
    handleVideoEnded,
    handleVideoError,
    expandedActiveVideo,
    expandedVideoError,
    expandedLightToDarkRef,
    expandedDarkToLightRef,
    handleExpandedVideoEnded,
    handleExpandedVideoError,
    setVisibleChannel,
  } = useThemeTransition()
  const [expandedImageError, setExpandedImageError] = useState(false)

  useEffect(() => {
    setVisibleChannel(isExpanded ? "expanded" : "small")
  }, [isExpanded, setVisibleChannel])

  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 z-0 overflow-hidden">
      {/* Layer 0 — instant underlay: always painted so the background is never blank,
          not just an error fallback. Videos paint over it once ready. */}
      <GradientFallback theme={theme} />

      {/* Layer 1 — small-mode pair: stays mounted while expanded, only hidden. */}
      {!videoError && (
        <div
          className={`absolute inset-0 transition-opacity duration-200 ${
            isExpanded ? "opacity-0" : "opacity-100"
          }`}
        >
          <video
            ref={lightToDarkRef}
            src={LIGHT_TO_DARK_SRC}
            muted
            playsInline
            preload="auto"
            loop={false}
            onEnded={handleVideoEnded}
            onError={handleVideoError}
            onLoadedMetadata={(e) => {
              e.currentTarget.currentTime = 0
            }}
            className={`absolute inset-0 h-full w-full object-cover object-center ${
              activeVideo === "light-to-dark" ? "opacity-100" : "opacity-0"
            }`}
          />
          <video
            ref={darkToLightRef}
            src={DARK_TO_LIGHT_SRC}
            muted
            playsInline
            preload="auto"
            loop={false}
            onEnded={handleVideoEnded}
            onError={handleVideoError}
            onLoadedMetadata={(e) => {
              e.currentTarget.currentTime = 0
            }}
            className={`absolute inset-0 h-full w-full object-cover object-center ${
              activeVideo === "dark-to-light" ? "opacity-100" : "opacity-0"
            }`}
          />
        </div>
      )}

      {/* Layer 2 — expanded pair: also always mounted, shown only while expanded. */}
      <div
        className={`absolute inset-0 transition-opacity duration-200 ${
          isExpanded ? "opacity-100" : "opacity-0"
        }`}
      >
        {expandedVideoError ? (
          expandedImageError ? null : (
            // eslint-disable-next-line @next/next/no-img-element -- background fallback, not content
            <img
              src={EXPANDED_POSTER_SRC[theme]}
              alt=""
              aria-hidden
              onError={() => setExpandedImageError(true)}
              className="absolute inset-0 h-full w-full object-cover object-center"
            />
          )
        ) : (
          <>
            <video
              ref={expandedLightToDarkRef}
              src={EXPANDED_LIGHT_TO_DARK_SRC}
              poster={EXPANDED_POSTER_SRC.light}
              muted
              playsInline
              preload="auto"
              loop={false}
              onEnded={handleExpandedVideoEnded}
              onError={handleExpandedVideoError}
              onLoadedMetadata={(e) => {
                e.currentTarget.currentTime = 0
              }}
              className={`absolute inset-0 h-full w-full object-cover object-center ${
                expandedActiveVideo === "light-to-dark" ? "opacity-100" : "opacity-0"
              }`}
            />
            <video
              ref={expandedDarkToLightRef}
              src={EXPANDED_DARK_TO_LIGHT_SRC}
              poster={EXPANDED_POSTER_SRC.dark}
              muted
              playsInline
              preload="auto"
              loop={false}
              onEnded={handleExpandedVideoEnded}
              onError={handleExpandedVideoError}
              onLoadedMetadata={(e) => {
                e.currentTarget.currentTime = 0
              }}
              className={`absolute inset-0 h-full w-full object-cover object-center ${
                expandedActiveVideo === "dark-to-light" ? "opacity-100" : "opacity-0"
              }`}
            />
          </>
        )}
      </div>

      {/* Theme overlay — dims the background video uniformly (flat tint, no shaped glow) so it
          stays readable behind the bubbles/header/input without an odd spotlight in the center. */}
      <div
        className="absolute inset-0 z-[1] transition-opacity duration-[400ms] ease"
        style={{
          backgroundColor: "rgb(var(--color-background))",
          opacity: theme === "dark" ? 0.5 : 0.42,
        }}
      />
    </div>
  )
}
