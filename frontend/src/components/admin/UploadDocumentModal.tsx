"use client"

import { useState } from "react"
import type { UploadDocumentCategory } from "@/types/admin"
import { Button } from "@/components/ui/Button"
import { DocumentTypeSelector } from "./DocumentTypeSelector"
import { UploadDropzone } from "./UploadDropzone"

interface UploadDocumentModalProps {
  onClose: () => void
  onUpload: (data: { category: UploadDocumentCategory; file: File; title: string }) => void
}

export function UploadDocumentModal({ onClose, onUpload }: UploadDocumentModalProps) {
  const [category, setCategory] = useState<UploadDocumentCategory | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState("")

  const canSubmit = category !== null && file !== null

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!category || !file) return
    onUpload({ category, file, title: title.trim() || file.name })
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <form
        onSubmit={handleSubmit}
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-[90vh] w-full max-w-xl flex-col rounded-3xl border border-hairline bg-surface shadow-premium transition-colors duration-300"
      >
        <div className="flex shrink-0 items-start justify-between border-b border-hairline p-6 pb-4">
          <div>
            <h2 className="text-base font-semibold text-ink">Unggah Dokumen</h2>
            <p className="text-xs text-ink-muted">
              Dokumen akan masuk status &ldquo;Menunggu Review&rdquo; sebelum aktif digunakan.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Tutup"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-ink-muted transition-colors duration-300 hover:bg-surface-elevated hover:text-ink"
          >
            <CloseIcon className="h-4 w-4" />
          </button>
        </div>

        <div className="flex flex-col gap-5 overflow-y-auto p-6">
          <div className="flex flex-col gap-2">
            <label className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
              Jenis Dokumen
            </label>
            <DocumentTypeSelector value={category} onChange={setCategory} />
          </div>

          <div className="flex flex-col gap-2">
            <label className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
              File
            </label>
            <UploadDropzone file={file} onFileSelect={setFile} />
          </div>

          <div className="flex flex-col gap-2">
            <label htmlFor="doc-title" className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
              Judul Dokumen (opsional)
            </label>
            <input
              id="doc-title"
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={file?.name ?? "Contoh: Panduan SPMB 2026"}
              className="rounded-xl border border-hairline bg-surface-elevated px-3 py-2 text-sm text-ink placeholder:text-ink-muted focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
        </div>

        <div className="flex shrink-0 justify-end gap-2 border-t border-hairline p-6 pt-4">
          <Button type="button" variant="secondary" onClick={onClose}>
            Batal
          </Button>
          <Button type="submit" variant="primary" disabled={!canSubmit}>
            Unggah Dokumen
          </Button>
        </div>
      </form>
    </div>
  )
}

function CloseIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" className={className} aria-hidden="true">
      <path d="M5 5l10 10M15 5L5 15" />
    </svg>
  )
}
