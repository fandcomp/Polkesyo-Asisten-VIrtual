"use client"

interface MessageInputProps {
  value: string
  onChange: (value: string) => void
  onSubmit: (e: React.FormEvent) => void
  disabled: boolean
}

export function MessageInput({ value, onChange, onSubmit, disabled }: MessageInputProps) {
  return (
    <form
      onSubmit={onSubmit}
      className="relative z-10 border-t border-[rgba(255,255,255,0.30)] p-4 backdrop-blur-[3px] transition-colors duration-300"
      style={{
        backgroundColor: "rgba(255,255,255,0.32)",
        boxShadow: "0 -2px 16px rgba(0,0,0,0.06)",
      }}
    >
      <div className="flex items-center gap-2">
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Tulis pertanyaan Anda..."
          disabled={disabled}
          className="input-glass flex-1 rounded-full px-5 py-3 text-sm outline-none backdrop-blur-[3px] disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={disabled || !value.trim()}
          aria-label="Kirim pesan"
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-gold/60 bg-gradient-to-br from-[#C8D600] to-[#00AEB3] text-white shadow-premium transition-all duration-300 hover:brightness-110 active:scale-95 disabled:opacity-40 disabled:shadow-none"
        >
          <ArrowRightIcon className="h-4 w-4" />
        </button>
      </div>
    </form>
  )
}

function ArrowRightIcon({ className }: { className?: string }) {
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
      <path d="M4 10h12M11 5l5 5-5 5" />
    </svg>
  )
}
