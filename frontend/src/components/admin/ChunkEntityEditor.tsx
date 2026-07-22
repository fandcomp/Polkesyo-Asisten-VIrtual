"use client"

import { useEffect, useState } from "react"
import type { AdminChunkEntity } from "@/types/admin"
import { ApiClient, type ChunkEntityResponse } from "@/lib/apiClient"

interface ChunkEntityEditorProps {
  chunkId: string
  /** Locks the editor once the chunk itself is approved/rejected — same reasoning as the
   *  summary textarea's `disabled={isDecided}` in ChunkReviewCard. */
  readOnly: boolean
}

const STATUS_LABEL: Record<AdminChunkEntity["status"], string> = {
  detected: "Terdeteksi",
  confirmed: "Dikonfirmasi",
  edited: "Dikoreksi",
  rejected: "Ditolak",
}

// Raw entity_type values match GraphService.ALLOWED_ENTITY_TYPES (PascalCase, graph-schema
// identifiers) — readable here as e.g. "Program Studi" instead of the technical "ProgramStudi"
// admins would otherwise see verbatim. Falls back to the raw value for any type not yet mapped
// (e.g. if ALLOWED_ENTITY_TYPES grows before this list is updated), so nothing ever renders blank.
const ENTITY_TYPE_LABEL: Record<string, string> = {
  ProgramStudi: "Program Studi",
  JalurPendaftaran: "Jalur Pendaftaran",
  TahapSeleksi: "Tahap Seleksi",
  Persyaratan: "Persyaratan",
  Jadwal: "Jadwal",
  Biaya: "Biaya",
}

function entityTypeLabel(type: string): string {
  return ENTITY_TYPE_LABEL[type] ?? type
}

function mapEntity(e: ChunkEntityResponse): AdminChunkEntity {
  return {
    id: e.id,
    chunkId: e.chunk_id,
    documentId: e.document_id,
    entityType: e.entity_type,
    detectedText: e.detected_text,
    correctedText: e.corrected_text ?? undefined,
    correctedType: e.corrected_type ?? undefined,
    source: e.source,
    status: e.status,
  }
}

export function ChunkEntityEditor({ chunkId, readOnly }: ChunkEntityEditorProps) {
  const [entities, setEntities] = useState<AdminChunkEntity[]>([])
  const [entityTypes, setEntityTypes] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editText, setEditText] = useState("")
  const [editType, setEditType] = useState("")
  const [pendingId, setPendingId] = useState<string | null>(null)
  const [showAddForm, setShowAddForm] = useState(false)
  const [newType, setNewType] = useState("")
  const [newText, setNewText] = useState("")

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    Promise.all([ApiClient.getChunkEntities(chunkId), ApiClient.getEntityTypes()])
      .then(([entitiesRes, types]) => {
        if (cancelled) return
        // Rejected rows stay in Postgres for the audit trail (never hard-deleted) but have
        // no place in the admin's working list once dismissed.
        setEntities(entitiesRes.entities.map(mapEntity).filter((e) => e.status !== "rejected"))
        setEntityTypes(types)
        setNewType((prev) => prev || types[0] || "")
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Gagal memuat entitas.")
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [chunkId])

  const startEdit = (entity: AdminChunkEntity) => {
    setEditingId(entity.id)
    setEditText(entity.correctedText ?? entity.detectedText)
    setEditType(entity.correctedType ?? entity.entityType)
  }

  const cancelEdit = () => setEditingId(null)

  const saveEdit = async (entity: AdminChunkEntity) => {
    setPendingId(entity.id)
    try {
      const updated = await ApiClient.editChunkEntity(chunkId, entity.id, {
        correctedText: editText !== entity.detectedText ? editText : undefined,
        correctedType: editType !== entity.entityType ? editType : undefined,
      })
      setEntities((prev) => prev.map((e) => (e.id === entity.id ? mapEntity(updated) : e)))
      setEditingId(null)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Gagal menyimpan koreksi entitas.")
    } finally {
      setPendingId(null)
    }
  }

  const confirmEntity = async (entity: AdminChunkEntity) => {
    setPendingId(entity.id)
    try {
      const updated = await ApiClient.confirmChunkEntity(chunkId, entity.id)
      setEntities((prev) => prev.map((e) => (e.id === entity.id ? mapEntity(updated) : e)))
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Gagal mengonfirmasi entitas.")
    } finally {
      setPendingId(null)
    }
  }

  const rejectEntity = async (entity: AdminChunkEntity) => {
    setPendingId(entity.id)
    try {
      await ApiClient.rejectChunkEntity(chunkId, entity.id)
      setEntities((prev) => prev.filter((e) => e.id !== entity.id))
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Gagal menolak entitas.")
    } finally {
      setPendingId(null)
    }
  }

  const addEntity = async () => {
    if (!newText.trim() || !newType) return
    setPendingId("__new__")
    try {
      const created = await ApiClient.addChunkEntity(chunkId, newType, newText.trim())
      setEntities((prev) => [...prev, mapEntity(created)])
      setNewText("")
      setShowAddForm(false)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Gagal menambah entitas.")
    } finally {
      setPendingId(null)
    }
  }

  if (loading) {
    return <p className="text-xs text-ink-muted">Memuat entitas…</p>
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
          Entitas Terdeteksi
        </p>
        {!readOnly && (
          <button
            type="button"
            onClick={() => setShowAddForm((v) => !v)}
            className="text-xs font-semibold text-primary hover:underline"
          >
            {showAddForm ? "Batal" : "+ Tambah Entitas"}
          </button>
        )}
      </div>

      {error && <p className="text-xs text-danger">{error}</p>}

      {entities.length === 0 && !showAddForm && (
        <p className="text-xs text-ink-muted">Tidak ada entitas terdeteksi.</p>
      )}

      {entities.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {entities.map((entity) => {
            const isEditing = editingId === entity.id
            const isPending = pendingId === entity.id
            const displayText = entity.correctedText ?? entity.detectedText
            const displayType = entity.correctedType ?? entity.entityType

            if (isEditing) {
              return (
                <div
                  key={entity.id}
                  className="flex flex-wrap items-center gap-1.5 rounded-full border border-primary/50 bg-surface-elevated px-2 py-1"
                >
                  <select
                    value={editType}
                    onChange={(e) => setEditType(e.target.value)}
                    aria-label="Tipe entitas"
                    className="rounded-lg border border-hairline bg-surface px-1.5 py-0.5 text-xs text-ink"
                  >
                    {entityTypes.map((t) => (
                      <option key={t} value={t}>
                        {entityTypeLabel(t)}
                      </option>
                    ))}
                  </select>
                  <input
                    value={editText}
                    onChange={(e) => setEditText(e.target.value)}
                    aria-label="Teks entitas"
                    className="w-32 rounded-lg border border-hairline bg-surface px-1.5 py-0.5 text-xs text-ink"
                  />
                  <button
                    type="button"
                    disabled={isPending}
                    onClick={() => saveEdit(entity)}
                    className="text-xs font-semibold text-primary hover:underline disabled:opacity-50"
                  >
                    Simpan
                  </button>
                  <button
                    type="button"
                    onClick={cancelEdit}
                    className="text-xs text-ink-muted hover:underline"
                  >
                    Batal
                  </button>
                </div>
              )
            }

            return (
              <span
                key={entity.id}
                className="flex items-center gap-1.5 rounded-full border border-primary/30 bg-surface-elevated px-2.5 py-0.5 text-xs text-primary"
              >
                <span title={STATUS_LABEL[entity.status]}>
                  {entityTypeLabel(displayType)}: {displayText}
                </span>
                {entity.status === "edited" && (
                  <span className="text-[10px] text-ink-muted">(dikoreksi)</span>
                )}
                {!readOnly && (
                  <span className="flex items-center gap-1">
                    {entity.status === "detected" && (
                      <button
                        type="button"
                        disabled={isPending}
                        onClick={() => confirmEntity(entity)}
                        aria-label={`Konfirmasi entitas ${displayText}`}
                        title="Konfirmasi"
                        className="text-ink-muted hover:text-primary disabled:opacity-50"
                      >
                        ✓
                      </button>
                    )}
                    <button
                      type="button"
                      disabled={isPending}
                      onClick={() => startEdit(entity)}
                      aria-label={`Ubah entitas ${displayText}`}
                      title="Ubah"
                      className="text-ink-muted hover:text-primary disabled:opacity-50"
                    >
                      ✎
                    </button>
                    <button
                      type="button"
                      disabled={isPending}
                      onClick={() => rejectEntity(entity)}
                      aria-label={`Tolak entitas ${displayText}`}
                      title="Tolak"
                      className="text-ink-muted hover:text-danger disabled:opacity-50"
                    >
                      ×
                    </button>
                  </span>
                )}
              </span>
            )
          })}
        </div>
      )}

      {!readOnly && showAddForm && (
        <div className="flex flex-wrap items-center gap-1.5 rounded-xl border border-hairline bg-surface-elevated p-2">
          <select
            value={newType}
            onChange={(e) => setNewType(e.target.value)}
            aria-label="Tipe entitas baru"
            className="rounded-lg border border-hairline bg-surface px-1.5 py-1 text-xs text-ink"
          >
            {entityTypes.map((t) => (
              <option key={t} value={t}>
                {entityTypeLabel(t)}
              </option>
            ))}
          </select>
          <input
            value={newText}
            onChange={(e) => setNewText(e.target.value)}
            placeholder="Nama/teks entitas"
            aria-label="Teks entitas baru"
            className="min-w-[8rem] flex-1 rounded-lg border border-hairline bg-surface px-1.5 py-1 text-xs text-ink placeholder:text-ink-muted"
          />
          <button
            type="button"
            disabled={pendingId === "__new__" || !newText.trim()}
            onClick={addEntity}
            className="text-xs font-semibold text-primary hover:underline disabled:opacity-50"
          >
            Tambah
          </button>
        </div>
      )}
    </div>
  )
}
