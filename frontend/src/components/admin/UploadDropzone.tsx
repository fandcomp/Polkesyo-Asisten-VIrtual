"use client"

import { useRef, useState } from "react"

interface UploadDropzoneProps {
  file: File | null
  onFileSelect: (file: File | null) => void
  accept?: string
  maxSizeMb?: number
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function UploadDropzone({
  file,
  onFileSelect,
  accept = ".pdf,.docx,.html",
  maxSizeMb = 25,
}: UploadDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [sizeError, setSizeError] = useState<string | null>(null)

  const handleFile = (selected: File | null) => {
    setSizeError(null)
    if (selected && selected.size > maxSizeMb * 1024 * 1024) {
      setSizeError(`Ukuran file melebihi batas ${maxSizeMb} MB.`)
      return
    }
    onFileSelect(selected)
  }

  if (file) {
    return (
      <div className="flex items-center justify-between gap-3 rounded-2xl border border-hairline bg-surface-elevated p-4">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-primary/30 bg-surface text-primary">
            <FileIcon className="h-4.5 w-4.5" />
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-ink">{file.name}</p>
            <p className="text-xs text-ink-muted">{formatFileSize(file.size)}</p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => handleFile(null)}
          aria-label="Hapus file"
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-ink-muted transition-colors duration-300 hover:bg-surface hover:text-danger"
        >
          <CloseIcon className="h-3.5 w-3.5" />
        </button>
      </div>
    )
  }

  return (
    <div>
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault()
          setIsDragging(true)
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setIsDragging(false)
          handleFile(e.dataTransfer.files?.[0] ?? null)
        }}
        className={`flex w-full flex-col items-center gap-2 rounded-2xl border-2 border-dashed p-6 text-center transition-colors duration-300 ${
          isDragging
            ? "border-primary bg-surface-elevated"
            : "border-hairline bg-surface hover:bg-surface-elevated"
        }`}
      >
        <span className="flex h-10 w-10 items-center justify-center rounded-full border border-gold/50 bg-surface-elevated text-primary">
          <UploadIcon className="h-4.5 w-4.5" />
        </span>
        <p className="text-sm font-medium text-ink">Tarik file ke sini atau klik untuk memilih</p>
        <p className="text-xs text-ink-muted">PDF, DOCX, atau HTML · maks. {maxSizeMb} MB</p>
      </button>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => handleFile(e.target.files?.[0] ?? null)}
      />
      {sizeError && <p className="mt-2 text-xs text-danger">{sizeError}</p>}
    </div>
  )
}

function UploadIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="M10 13V4M6.5 7.5L10 4l3.5 3.5" />
      <path d="M4 14v1.5a1 1 0 001 1h10a1 1 0 001-1V14" />
    </svg>
  )
}

function FileIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="M5.5 2.5h6l3 3v11a1 1 0 01-1 1h-8a1 1 0 01-1-1v-13a1 1 0 011-1z" />
      <path d="M11.5 2.5v3h3" />
    </svg>
  )
}

function CloseIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" className={className} aria-hidden="true">
      <path d="M5 5l10 10M15 5L5 15" />
    </svg>
  )
}
