export type DocumentStatus =
  | "discovered"
  | "downloaded"
  | "extracted"
  | "chunked"
  | "summarized"
  | "pending_review"
  | "approved"
  | "indexed"
  | "active"
  | "rejected"
  | "needs_revision"
  | "superseded"
  | "archived"

// Values match backend DocumentClassifier.ALLOWED_TYPES exactly (see
// backend/app/services/document_classifier.py) so the selected label can be
// sent straight through as the document_type override — no translation table.
export type UploadDocumentCategory =
  | "Pengumuman"
  | "Pedoman"
  | "Regulasi"
  | "SOP"
  | "Form"
  | "Brosur SPMB"
  | "FAQ"

export const UPLOAD_DOCUMENT_CATEGORIES: {
  value: UploadDocumentCategory
  label: string
  description: string
}[] = [
  { value: "Pengumuman", label: "Pengumuman", description: "Pengumuman resmi, hasil seleksi" },
  { value: "Pedoman", label: "Pedoman", description: "Panduan atau buku pedoman resmi" },
  { value: "Regulasi", label: "Regulasi", description: "Peraturan, tata tertib, kebijakan resmi" },
  { value: "SOP", label: "SOP", description: "Prosedur operasional standar, alur layanan" },
  { value: "Form", label: "Form", description: "Formulir, template pendaftaran" },
  { value: "Brosur SPMB", label: "Brosur SPMB", description: "Brosur atau leaflet informasi SPMB" },
  { value: "FAQ", label: "FAQ", description: "Pertanyaan yang sering diajukan" },
]

export interface AdminDocument {
  id: string
  title: string
  documentType: string
  status: DocumentStatus
  createdAt: string
  pendingChunkCount: number
  /** Total chunks ever created for this document (0 = never ingested). Demo mode always reports 0. */
  chunkCount: number
  /** Latest DocumentVersion UUID, used to trigger ingestion. Absent in demo mode. */
  latestVersionId?: string
}

export type ChunkStatus =
  | "created"
  | "summary_drafted"
  | "pending_review"
  | "approved"
  | "rejected"
  | "needs_revision"
  | "indexed"
  | "active"
  | "superseded"
  | "archived"

export interface AdminChunk {
  id: string
  documentId: string
  page?: number
  section?: string
  originalText: string
  llmSummaryDraft: string
  adminEditedSummary?: string
  status: ChunkStatus
  riskFlags: string[]
  detectedEntities: string[]
}

// Durable, per-chunk, admin-editable entity record (chunk_entities table). Values match
// GraphService.ALLOWED_ENTITY_TYPES exactly (see backend/app/services/graph_service.py) —
// fetched from GET /admin/entity-types rather than hardcoded, so this list never drifts.
export type ChunkEntitySource = "llm_detected" | "admin_added"
export type ChunkEntityStatus = "detected" | "confirmed" | "edited" | "rejected"

export interface AdminChunkEntity {
  id: string
  chunkId: string
  documentId: string
  entityType: string
  /** Immutable original detection (or the admin-typed text when source === "admin_added"). */
  detectedText: string
  /** Admin correction of the text/terminology, if any. */
  correctedText?: string
  /** Admin correction of the type, if any. */
  correctedType?: string
  source: ChunkEntitySource
  status: ChunkEntityStatus
}

export type VisualChunkType = "text" | "image" | "table_image" | "diagram" | "scanned_region" | "mixed"

export type VisualChunkStatus =
  | "pending_review"
  | "approved"
  | "rejected"
  | "needs_revision"
  | "indexed"
  | "active"
  | "archived"

export interface AdminVisualChunk {
  id: string
  documentId: string
  page?: number
  chunkType: VisualChunkType
  imageUrl: string
  rawVisualDescription: string
  visibleTextDraft: string
  uncertaintyNotes?: string
  confidenceScore?: number
  riskFlags: string[]
  status: VisualChunkStatus
}

// Structure-aware document extraction plan (form/attachment zones -> standalone .docx).
export type DocumentFormZoneType = "form_text" | "form_vision"

export type DocumentFormStatus =
  | "pending_review"
  | "approved"
  | "rejected"
  | "needs_revision"
  | "active"
  | "archived"

export interface AdminDocumentForm {
  id: string
  documentId: string
  zoneType: DocumentFormZoneType
  formTitle: string
  sourcePageStart: number
  sourcePageEnd: number
  extractionMethod: "text" | "vision"
  status: DocumentFormStatus
}
