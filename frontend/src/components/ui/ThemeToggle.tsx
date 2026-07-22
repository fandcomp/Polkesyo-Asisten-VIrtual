"use client"

import { useThemeTransition } from "@/lib/useThemeTransition"

export function ThemeToggle() {
  const { theme, isThemeTransitioning, requestThemeChange } = useThemeTransition()
  const isDark = theme === "dark"

  return (
    <button
      type="button"
      role="switch"
      aria-checked={isDark}
      aria-label={isDark ? "Aktifkan mode terang" : "Aktifkan mode gelap"}
      onClick={requestThemeChange}
      disabled={isThemeTransitioning}
      className="relative flex h-8 w-16 shrink-0 items-center rounded-full border border-gold/70 bg-surface-elevated p-1 shadow-sm transition-colors duration-300 disabled:cursor-wait disabled:opacity-70"
    >
      <span
        className={`absolute top-1 left-1 h-6 w-6 rounded-full bg-gradient-to-br from-primary to-accent shadow transition-transform duration-300 ease-out ${
          isDark ? "translate-x-8" : "translate-x-0"
        }`}
        aria-hidden="true"
      />
      <span className="relative z-10 flex w-full items-center justify-between px-0.5">
        <SunIcon isActive={!isDark} />
        <MoonIcon isActive={isDark} />
      </span>
      {isThemeTransitioning && (
        <span
          className="absolute inset-0 flex items-center justify-center rounded-full bg-surface-elevated/70"
          aria-hidden="true"
        >
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-primary/30 border-t-primary" />
        </span>
      )}
    </button>
  )
}

function SunIcon({ isActive }: { isActive: boolean }) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      className={`h-3.5 w-3.5 transition-colors duration-300 ${
        isActive ? "text-white" : "text-ink-muted"
      }`}
      aria-hidden="true"
    >
      <circle cx="10" cy="10" r="3.2" />
      <path d="M10 3v1.4M10 15.6V17M17 10h-1.4M4.4 10H3M14.7 5.3l-1 1M6.3 13.7l-1 1M14.7 14.7l-1-1M6.3 6.3l-1-1" />
    </svg>
  )
}

function MoonIcon({ isActive }: { isActive: boolean }) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="currentColor"
      className={`h-3.5 w-3.5 transition-colors duration-300 ${
        isActive ? "text-white" : "text-ink-muted"
      }`}
      aria-hidden="true"
    >
      <path d="M15.5 12.3A6.3 6.3 0 018.2 4.6a.6.6 0 00-.8-.7 7.5 7.5 0 108.8 8.8.6.6 0 00-.7-.4z" />
    </svg>
  )
}
