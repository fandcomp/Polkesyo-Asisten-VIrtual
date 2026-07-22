"use client"

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type RefObject,
} from "react"
import { useTheme } from "./useTheme"

export type ActiveVideo = "light-to-dark" | "dark-to-light"

// The transition clips play sped up in both directions so a theme switch feels instant
// rather than waiting out the clip's native (slow) runtime.
const TRANSITION_PLAYBACK_RATE = 2.75

interface ThemeTransitionContextValue {
  theme: "light" | "dark"
  isThemeTransitioning: boolean
  reducedMotion: boolean
  videoError: boolean
  activeVideo: ActiveVideo
  lightToDarkRef: RefObject<HTMLVideoElement | null>
  darkToLightRef: RefObject<HTMLVideoElement | null>
  // Second, independent channel for the expanded (maximized) chatbot background — a separate
  // pair of clips (see ChatBackground.tsx). Since the instant-readiness rework BOTH channels
  // stay mounted at all times (hidden with CSS opacity), so ChatBackground reports which one
  // is actually visible via setVisibleChannel and a theme toggle animates that channel; the
  // hidden channel snaps to its settled frame through the settle effect below.
  expandedVideoError: boolean
  expandedActiveVideo: ActiveVideo
  expandedLightToDarkRef: RefObject<HTMLVideoElement | null>
  expandedDarkToLightRef: RefObject<HTMLVideoElement | null>
  setVisibleChannel: (channel: "small" | "expanded") => void
  requestThemeChange: () => void
  handleVideoEnded: () => void
  handleVideoError: () => void
  handleExpandedVideoEnded: () => void
  handleExpandedVideoError: () => void
}

const ThemeTransitionContext = createContext<ThemeTransitionContextValue | null>(null)

export function ThemeTransitionProvider({ children }: { children: React.ReactNode }) {
  const { theme, toggleTheme } = useTheme()
  const [isThemeTransitioning, setIsThemeTransitioning] = useState(false)
  const [reducedMotion, setReducedMotion] = useState(false)

  const [activeVideo, setActiveVideo] = useState<ActiveVideo>(
    theme === "light" ? "light-to-dark" : "dark-to-light"
  )
  const [videoError, setVideoError] = useState(false)
  const lightToDarkRef = useRef<HTMLVideoElement | null>(null)
  const darkToLightRef = useRef<HTMLVideoElement | null>(null)
  const pendingCommitRef = useRef(false)

  const [expandedActiveVideo, setExpandedActiveVideo] = useState<ActiveVideo>(
    theme === "light" ? "light-to-dark" : "dark-to-light"
  )
  const [expandedVideoError, setExpandedVideoError] = useState(false)
  const expandedLightToDarkRef = useRef<HTMLVideoElement | null>(null)
  const expandedDarkToLightRef = useRef<HTMLVideoElement | null>(null)
  const pendingExpandedCommitRef = useRef(false)

  // Which channel the user can actually see right now — reported by ChatBackground whenever
  // isExpanded changes. A ref (not state): reading it inside requestThemeChange must not
  // re-create the callback or re-render anything.
  const visibleChannelRef = useRef<"small" | "expanded">("small")
  const setVisibleChannel = useCallback((channel: "small" | "expanded") => {
    visibleChannelRef.current = channel
  }, [])

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)")
    setReducedMotion(mq.matches)
    const handler = (e: MediaQueryListEvent) => setReducedMotion(e.matches)
    mq.addEventListener("change", handler)
    return () => mq.removeEventListener("change", handler)
  }, [])

  // Both channels' clips share the same boundary-frame contract, so whenever we're not
  // mid-transition, the video to show is purely a function of theme — settle both channels in
  // parallel; whichever one isn't currently mounted (ref null) is a harmless no-op.
  useEffect(() => {
    if (isThemeTransitioning) return
    const nextActive: ActiveVideo = theme === "light" ? "light-to-dark" : "dark-to-light"

    setActiveVideo(nextActive)
    const ref = nextActive === "light-to-dark" ? lightToDarkRef : darkToLightRef
    if (ref.current) ref.current.currentTime = 0

    setExpandedActiveVideo(nextActive)
    const expandedRef = nextActive === "light-to-dark" ? expandedLightToDarkRef : expandedDarkToLightRef
    if (expandedRef.current) expandedRef.current.currentTime = 0
  }, [theme, isThemeTransitioning])

  const requestThemeChange = useCallback(() => {
    if (isThemeTransitioning) return

    if (reducedMotion) {
      toggleTheme()
      return
    }

    const sourceVideo: ActiveVideo = theme === "light" ? "light-to-dark" : "dark-to-light"

    // Both channels are always mounted now — animate the one the user can actually see
    // (reported by ChatBackground via setVisibleChannel); fall back to the other if the
    // visible one has errored or isn't mounted. The non-animated channel snaps to its
    // settled frame via the settle effect when the theme commits.
    const smallRef = sourceVideo === "light-to-dark" ? lightToDarkRef : darkToLightRef
    const expandedRef = sourceVideo === "light-to-dark" ? expandedLightToDarkRef : expandedDarkToLightRef

    type Channel = { ref: RefObject<HTMLVideoElement | null>; setActive: (v: ActiveVideo) => void; pendingCommit: RefObject<boolean>; onErrorFallback: () => void }
    const smallChannel: Channel | null = !videoError && smallRef.current
      ? { ref: smallRef, setActive: setActiveVideo, pendingCommit: pendingCommitRef, onErrorFallback: () => setVideoError(true) }
      : null
    const expandedChannel: Channel | null = !expandedVideoError && expandedRef.current
      ? { ref: expandedRef, setActive: setExpandedActiveVideo, pendingCommit: pendingExpandedCommitRef, onErrorFallback: () => setExpandedVideoError(true) }
      : null

    const channel: Channel | null =
      visibleChannelRef.current === "expanded"
        ? expandedChannel ?? smallChannel
        : smallChannel ?? expandedChannel

    if (!channel) {
      toggleTheme()
      return
    }

    const { ref, setActive, pendingCommit, onErrorFallback } = channel
    setIsThemeTransitioning(true)
    setActive(sourceVideo)
    pendingCommit.current = true
    ref.current!.currentTime = 0
    ref.current!.playbackRate = TRANSITION_PLAYBACK_RATE
    ref.current!.play().catch(() => {
      pendingCommit.current = false
      onErrorFallback()
      setIsThemeTransitioning(false)
      toggleTheme()
    })
  }, [theme, isThemeTransitioning, reducedMotion, videoError, expandedVideoError, toggleTheme])

  const handleVideoEnded = useCallback(() => {
    if (!pendingCommitRef.current) return
    pendingCommitRef.current = false
    toggleTheme()
    setIsThemeTransitioning(false)
  }, [toggleTheme])

  const handleVideoError = useCallback(() => {
    setVideoError(true)
    if (pendingCommitRef.current) {
      pendingCommitRef.current = false
      toggleTheme()
    }
    setIsThemeTransitioning(false)
  }, [toggleTheme])

  const handleExpandedVideoEnded = useCallback(() => {
    if (!pendingExpandedCommitRef.current) return
    pendingExpandedCommitRef.current = false
    toggleTheme()
    setIsThemeTransitioning(false)
  }, [toggleTheme])

  const handleExpandedVideoError = useCallback(() => {
    setExpandedVideoError(true)
    if (pendingExpandedCommitRef.current) {
      pendingExpandedCommitRef.current = false
      toggleTheme()
    }
    setIsThemeTransitioning(false)
  }, [toggleTheme])

  return (
    <ThemeTransitionContext.Provider
      value={{
        theme,
        isThemeTransitioning,
        reducedMotion,
        videoError,
        activeVideo,
        lightToDarkRef,
        darkToLightRef,
        expandedVideoError,
        expandedActiveVideo,
        expandedLightToDarkRef,
        expandedDarkToLightRef,
        setVisibleChannel,
        requestThemeChange,
        handleVideoEnded,
        handleVideoError,
        handleExpandedVideoEnded,
        handleExpandedVideoError,
      }}
    >
      {children}
    </ThemeTransitionContext.Provider>
  )
}

export function useThemeTransition(): ThemeTransitionContextValue {
  const ctx = useContext(ThemeTransitionContext)
  if (!ctx) {
    throw new Error("useThemeTransition must be used within a ThemeTransitionProvider")
  }
  return ctx
}
