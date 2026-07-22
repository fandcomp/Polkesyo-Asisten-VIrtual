"use client"

import { useState } from "react"
import { Button } from "@/components/ui/Button"
import { DocumentList } from "@/components/admin/DocumentList"
import { ChunkReviewQueue } from "@/components/admin/ChunkReviewQueue"
import { VisualChunkReviewQueue } from "@/components/admin/VisualChunkReviewQueue"
import { DocumentFormReviewQueue } from "@/components/admin/DocumentFormReviewQueue"
import { UploadDocumentModal } from "@/components/admin/UploadDocumentModal"
import { useAdminData } from "@/lib/useAdminData"

export default function AdminReviewPage() {
  const {
    mode,
    documents,
    selectedId,
    setSelectedId,
    selectedChunks,
    updateChunkStatus,
    bulkApprove,
    uploadDocument,
    ingestDocument,
    ingestingDocumentId,
    selectedVisualChunks,
    decideVisualChunk,
    selectedDocumentForms,
    decideDocumentForm,
  } = useAdminData()
  const [isUploadOpen, setIsUploadOpen] = useState(false)

  return (
    <div className="grid gap-6 md:grid-cols-[280px_1fr]">
      <aside className="flex flex-col gap-3 md:sticky md:top-6 md:self-start">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">Dokumen</p>
          <Button variant="primary" className="!px-3 !py-1.5 text-xs" onClick={() => setIsUploadOpen(true)}>
            + Unggah
          </Button>
        </div>
        <DocumentList
          documents={documents}
          selectedId={selectedId}
          onSelect={setSelectedId}
          onIngest={ingestDocument}
          ingestingDocumentId={ingestingDocumentId}
          canIngest={mode === "live"}
        />
      </aside>

      <section className="flex flex-col gap-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">Antrean Review Chunk</p>
        <ChunkReviewQueue
          chunks={selectedChunks}
          onApprove={(chunkId, summary) => updateChunkStatus(chunkId, "approved", summary)}
          onReject={(chunkId, summary) => updateChunkStatus(chunkId, "rejected", summary)}
          onNeedsRevision={(chunkId, summary) => updateChunkStatus(chunkId, "needs_revision", summary)}
          onBulkApprove={bulkApprove}
        />

        <p className="mt-2 text-xs font-semibold uppercase tracking-wide text-ink-muted">
          Antrean Review Chunk Visual
        </p>
        <VisualChunkReviewQueue
          chunks={selectedVisualChunks}
          onApprove={(chunkId, editedDescription) =>
            decideVisualChunk(chunkId, "approve", { editedSummary: editedDescription })
          }
          onReject={(chunkId, reason) => decideVisualChunk(chunkId, "reject", { reason })}
          onNeedsRevision={(chunkId, reason, editedDescription) =>
            decideVisualChunk(chunkId, "needs_revision", { reason, editedSummary: editedDescription })
          }
        />

        <p className="mt-2 text-xs font-semibold uppercase tracking-wide text-ink-muted">
          Antrean Review Formulir & Lampiran
        </p>
        <DocumentFormReviewQueue
          forms={selectedDocumentForms}
          onApprove={(formId, adminNotes) => decideDocumentForm(formId, "approve", { adminNotes })}
          onReject={(formId, reason) => decideDocumentForm(formId, "reject", { reason })}
          onNeedsRevision={(formId, reason) => decideDocumentForm(formId, "needs_revision", { reason })}
        />
      </section>

      {isUploadOpen && (
        <UploadDocumentModal
          onClose={() => setIsUploadOpen(false)}
          onUpload={(data) => {
            uploadDocument(data)
            setIsUploadOpen(false)
          }}
        />
      )}
    </div>
  )
}
