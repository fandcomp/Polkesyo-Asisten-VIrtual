"use client"

interface FloatingChatButtonProps {
  onClick: () => void
  disabled?: boolean
}

export function FloatingChatButton({ onClick, disabled }: FloatingChatButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label="Buka Asisten Kampus"
      className="group fixed bottom-6 right-6 z-40 rounded-full bg-gradient-to-r from-primary via-accent to-primary p-[2px] shadow-premium transition-transform duration-300 hover:-translate-y-1 active:scale-95 disabled:pointer-events-none disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gold"
    >
      <span className="flex items-center gap-2 rounded-full border border-gold/70 bg-primary px-5 py-3 text-white transition-colors duration-300 group-hover:border-gold">
        <DocumentCheckIcon className="h-5 w-5 shrink-0" />
        <span className="text-sm font-semibold">Tanya Layanan Kampus</span>
      </span>
    </button>
  )
}

function DocumentCheckIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M5.5 2.5h6l3 3v11a1 1 0 01-1 1h-8a1 1 0 01-1-1v-13a1 1 0 011-1z" />
      <path d="M11.5 2.5v3h3" />
      <path d="M7.3 11.2l1.6 1.6 3.3-3.6" />
    </svg>
  )
}
