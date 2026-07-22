"use client"

interface ResizeToggleButtonProps {
  isExpanded: boolean
  onToggle: () => void
  /** "light" matches WelcomeScreen's header (ink-muted on light bg); "dark" matches ChatUI's header (white/80 on teal). */
  variant: "light" | "dark"
}

export function ResizeToggleButton({ isExpanded, onToggle, variant }: ResizeToggleButtonProps) {
  const label = isExpanded ? "Perkecil chatbot" : "Perbesar chatbot"
  const variantClasses =
    variant === "dark"
      ? "text-white/80 hover:bg-white/15 hover:text-white"
      : "text-ink-muted hover:bg-surface-elevated hover:text-ink"

  return (
    <button
      type="button"
      onClick={onToggle}
      aria-label={label}
      title={label}
      className={`hidden h-8 w-8 items-center justify-center rounded-full transition-all duration-200 active:scale-90 sm:flex ${variantClasses}`}
    >
      {isExpanded ? <MinimizeIcon className="h-4 w-4" /> : <MaximizeIcon className="h-4 w-4" />}
    </button>
  )
}

function MaximizeIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M7 3H3v4M13 3h4v4M7 17H3v-4M13 17h4v-4" />
    </svg>
  )
}

function MinimizeIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M3 7V3h4M13 3h4v4M3 13v4h4M17 13v4h-4" />
    </svg>
  )
}
