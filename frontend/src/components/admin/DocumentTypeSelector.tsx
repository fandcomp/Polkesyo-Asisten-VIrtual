import { UPLOAD_DOCUMENT_CATEGORIES, type UploadDocumentCategory } from "@/types/admin"

interface DocumentTypeSelectorProps {
  value: UploadDocumentCategory | null
  onChange: (value: UploadDocumentCategory) => void
}

export function DocumentTypeSelector({ value, onChange }: DocumentTypeSelectorProps) {
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
      {UPLOAD_DOCUMENT_CATEGORIES.map((category) => {
        const isSelected = value === category.value
        return (
          <button
            key={category.value}
            type="button"
            onClick={() => onChange(category.value)}
            aria-pressed={isSelected}
            title={category.description}
            className={`flex items-center gap-2 rounded-xl border p-2.5 text-left transition-all duration-300 ${
              isSelected
                ? "border-primary bg-surface-elevated shadow-premium ring-1 ring-primary/30"
                : "border-hairline bg-surface hover:bg-surface-elevated"
            }`}
          >
            <span
              className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border transition-colors duration-300 ${
                isSelected
                  ? "border-gold/60 bg-gradient-to-br from-primary to-accent text-white"
                  : "border-hairline bg-surface-elevated text-ink-muted"
              }`}
            >
              <CategoryIcon category={category.value} className="h-3.5 w-3.5" />
            </span>
            <span className="truncate text-xs font-semibold text-ink">{category.label}</span>
          </button>
        )
      })}
    </div>
  )
}

function CategoryIcon({ category, className }: { category: UploadDocumentCategory; className?: string }) {
  const base = (
    <path d="M5.5 2.5h6l3 3v11a1 1 0 01-1 1h-8a1 1 0 01-1-1v-13a1 1 0 011-1z" />
  )

  if (category === "Regulasi") {
    return (
      <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
        {base}
        <path d="M11.5 2.5v3h3" />
        <circle cx="10" cy="12.3" r="2" />
        <path d="M9.1 13.9L8.6 16l1.4-.6 1.4.6-.5-2.1" />
      </svg>
    )
  }

  if (category === "Form") {
    return (
      <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
        {base}
        <path d="M11.5 2.5v3h3" />
        <path d="M6.8 10.2h1.4M9.4 10.2h3.8M6.8 12.6h1.4M9.4 12.6h3.8M6.8 15h1.4M9.4 15h3.8" />
      </svg>
    )
  }

  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      {base}
      <path d="M11.5 2.5v3h3" />
      <path d="M7 11.5l2.2 1.3v2.6L7 14.1v-2.6z" />
      <path d="M9.2 12.8h1.6a1.4 1.4 0 010 2.8H9.2" />
      <path d="M12.6 12.2a1.6 1.6 0 010 2" />
    </svg>
  )
}
