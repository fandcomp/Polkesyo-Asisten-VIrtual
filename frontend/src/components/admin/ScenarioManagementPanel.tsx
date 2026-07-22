"use client"

import { useEffect, useState } from "react"
import { Badge } from "@/components/ui/Badge"
import { Button } from "@/components/ui/Button"
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable"
import { useToast } from "@/components/ui/Toast"
import { ApiClient, type AdminScenarioResponse } from "@/lib/apiClient"

const EMPTY_DRAFT = { code: "", title: "", instruction: "", expected_task: "", order_index: 0 }

/** Admin CRUD for participant-study scenarios (S1/S2/...). No delete button by design — the
 * backend has no DELETE endpoint since asq_responses/sus_responses reference scenarios by id;
 * retiring a scenario means toggling it inactive via PATCH, not removing the row. */
export function ScenarioManagementPanel() {
  const { showToast } = useToast()
  const [scenarios, setScenarios] = useState<AdminScenarioResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState<AdminScenarioResponse | null>(null)
  const [editDraft, setEditDraft] = useState({ title: "", instruction: "", expected_task: "", order_index: 0 })
  const [saving, setSaving] = useState(false)
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [createDraft, setCreateDraft] = useState(EMPTY_DRAFT)

  const load = async () => {
    setLoading(true)
    try {
      const rows = await ApiClient.listEvaluationScenariosAdmin()
      setScenarios(rows.sort((a, b) => a.order_index - b.order_index))
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Gagal memuat skenario.", "error")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const startEdit = (scenario: AdminScenarioResponse) => {
    setEditing(scenario)
    setEditDraft({
      title: scenario.title,
      instruction: scenario.instruction,
      expected_task: scenario.expected_task ?? "",
      order_index: scenario.order_index,
    })
  }

  const saveEdit = async () => {
    if (!editing) return
    setSaving(true)
    try {
      await ApiClient.updateEvaluationScenario(editing.id, {
        title: editDraft.title,
        instruction: editDraft.instruction,
        expected_task: editDraft.expected_task || null,
        order_index: editDraft.order_index,
      })
      showToast("Skenario diperbarui.", "success")
      setEditing(null)
      await load()
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Gagal menyimpan perubahan.", "error")
    } finally {
      setSaving(false)
    }
  }

  const toggleActive = async (scenario: AdminScenarioResponse) => {
    try {
      await ApiClient.updateEvaluationScenario(scenario.id, { is_active: !scenario.is_active })
      showToast(scenario.is_active ? "Skenario dinonaktifkan." : "Skenario diaktifkan.", "success")
      await load()
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Gagal mengubah status.", "error")
    }
  }

  const createScenario = async () => {
    if (!createDraft.code.trim() || !createDraft.title.trim() || !createDraft.instruction.trim()) {
      showToast("Kode, judul, dan instruksi wajib diisi.", "error")
      return
    }
    setSaving(true)
    try {
      await ApiClient.createEvaluationScenario({
        code: createDraft.code.trim(),
        title: createDraft.title.trim(),
        instruction: createDraft.instruction.trim(),
        expected_task: createDraft.expected_task || null,
        order_index: createDraft.order_index,
      })
      showToast("Skenario baru dibuat.", "success")
      setCreateDraft(EMPTY_DRAFT)
      setShowCreateForm(false)
      await load()
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Gagal membuat skenario.", "error")
    } finally {
      setSaving(false)
    }
  }

  const columns: DataTableColumn<AdminScenarioResponse>[] = [
    { key: "code", header: "Kode", render: (s) => <span className="font-semibold text-ink">{s.code}</span> },
    { key: "title", header: "Judul", render: (s) => <span className="max-w-xs">{s.title}</span> },
    { key: "order", header: "Urutan", render: (s) => s.order_index },
    {
      key: "status",
      header: "Status",
      render: (s) => <Badge label={s.is_active ? "Aktif" : "Nonaktif"} tone={s.is_active ? "success" : "neutral"} />,
    },
    {
      key: "actions",
      header: "Aksi",
      render: (s) => (
        <div className="flex gap-2">
          <Button variant="secondary" className="px-3 py-1 text-xs" onClick={() => startEdit(s)}>
            Ubah
          </Button>
          <Button variant="secondary" className="px-3 py-1 text-xs" onClick={() => void toggleActive(s)}>
            {s.is_active ? "Nonaktifkan" : "Aktifkan"}
          </Button>
        </div>
      ),
    },
  ]

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between rounded-2xl border border-hairline bg-surface p-4 shadow-premium">
        <p className="text-sm text-ink-muted">
          {scenarios.length} skenario terdaftar — digunakan oleh alur partisipan di /evaluation.
        </p>
        <Button variant="secondary" className="px-3 py-1.5 text-xs" onClick={() => setShowCreateForm((v) => !v)}>
          {showCreateForm ? "Batal" : "Tambah Skenario"}
        </Button>
      </div>

      {showCreateForm && (
        <div className="flex flex-col gap-3 rounded-2xl border border-hairline bg-surface p-4 shadow-premium">
          <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">Skenario Baru</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <input
              placeholder="Kode (mis. S3)"
              value={createDraft.code}
              onChange={(e) => setCreateDraft({ ...createDraft, code: e.target.value })}
              className="rounded-xl border border-hairline bg-background px-3 py-2 text-sm text-ink"
            />
            <input
              placeholder="Judul"
              value={createDraft.title}
              onChange={(e) => setCreateDraft({ ...createDraft, title: e.target.value })}
              className="rounded-xl border border-hairline bg-background px-3 py-2 text-sm text-ink"
            />
          </div>
          <textarea
            placeholder="Instruksi untuk partisipan"
            value={createDraft.instruction}
            onChange={(e) => setCreateDraft({ ...createDraft, instruction: e.target.value })}
            rows={3}
            className="rounded-xl border border-hairline bg-background px-3 py-2 text-sm text-ink"
          />
          <input
            placeholder="Tugas yang diharapkan (opsional)"
            value={createDraft.expected_task}
            onChange={(e) => setCreateDraft({ ...createDraft, expected_task: e.target.value })}
            className="rounded-xl border border-hairline bg-background px-3 py-2 text-sm text-ink"
          />
          <div className="flex items-center gap-3">
            <label className="text-xs text-ink-muted" htmlFor="scenario-order-index">Urutan</label>
            <input
              id="scenario-order-index"
              type="number"
              value={createDraft.order_index}
              onChange={(e) => setCreateDraft({ ...createDraft, order_index: Number(e.target.value) })}
              className="w-20 rounded-xl border border-hairline bg-background px-3 py-2 text-sm text-ink"
            />
            <Button className="ml-auto px-4 py-2 text-xs" onClick={() => void createScenario()} disabled={saving}>
              Simpan Skenario
            </Button>
          </div>
        </div>
      )}

      {editing && (
        <div className="flex flex-col gap-3 rounded-2xl border border-hairline bg-surface p-4 shadow-premium">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
              Ubah Skenario {editing.code}
            </p>
            <button type="button" onClick={() => setEditing(null)} className="text-xs text-ink-muted hover:text-ink">
              Tutup
            </button>
          </div>
          <input
            value={editDraft.title}
            onChange={(e) => setEditDraft({ ...editDraft, title: e.target.value })}
            className="rounded-xl border border-hairline bg-background px-3 py-2 text-sm text-ink"
          />
          <textarea
            value={editDraft.instruction}
            onChange={(e) => setEditDraft({ ...editDraft, instruction: e.target.value })}
            rows={3}
            className="rounded-xl border border-hairline bg-background px-3 py-2 text-sm text-ink"
          />
          <input
            placeholder="Tugas yang diharapkan (opsional)"
            value={editDraft.expected_task}
            onChange={(e) => setEditDraft({ ...editDraft, expected_task: e.target.value })}
            className="rounded-xl border border-hairline bg-background px-3 py-2 text-sm text-ink"
          />
          <div className="flex items-center gap-3">
            <label className="text-xs text-ink-muted" htmlFor="scenario-edit-order-index">Urutan</label>
            <input
              id="scenario-edit-order-index"
              type="number"
              value={editDraft.order_index}
              onChange={(e) => setEditDraft({ ...editDraft, order_index: Number(e.target.value) })}
              className="w-20 rounded-xl border border-hairline bg-background px-3 py-2 text-sm text-ink"
            />
            <Button className="ml-auto px-4 py-2 text-xs" onClick={() => void saveEdit()} disabled={saving}>
              Simpan Perubahan
            </Button>
          </div>
        </div>
      )}

      <DataTable columns={columns} rows={scenarios} rowKey={(s) => s.id} loading={loading} />
    </div>
  )
}
