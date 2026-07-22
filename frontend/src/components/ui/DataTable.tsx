import type { ReactNode } from "react"
import { Button } from "@/components/ui/Button"

export interface DataTableColumn<T> {
  key: string
  header: string
  render: (row: T) => ReactNode
  className?: string
}

interface DataTableProps<T> {
  columns: DataTableColumn<T>[]
  rows: T[]
  rowKey: (row: T) => string
  loading?: boolean
  emptyMessage?: string
  onRowClick?: (row: T) => void
  /** Pagination — omit to render a plain, unpaginated table. */
  pagination?: {
    total: number
    limit: number
    offset: number
    onPageChange: (offset: number) => void
  }
}

/** Generic paginated/filterable table — the evaluation admin pages (technical logs, ACIF
 * traces, retrieval, citations, and later ASQ/SUS results) all need server-side pagination
 * over a plain row list, which no existing component in this codebase provided (the
 * chunk-review workflow's UI is single-document/small-dataset and has no table primitive). */
export function DataTable<T>({
  columns,
  rows,
  rowKey,
  loading = false,
  emptyMessage = "Tidak ada data.",
  onRowClick,
  pagination,
}: DataTableProps<T>) {
  return (
    <div className="overflow-hidden rounded-2xl border border-hairline bg-surface shadow-premium">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-hairline bg-surface-elevated">
              {columns.map((col) => (
                <th
                  key={col.key}
                  className={`whitespace-nowrap px-4 py-3 text-xs font-semibold uppercase tracking-wide text-ink-muted ${col.className ?? ""}`}
                >
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={columns.length} className="px-4 py-8 text-center text-ink-muted">
                  Memuat...
                </td>
              </tr>
            )}
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="px-4 py-8 text-center text-ink-muted">
                  {emptyMessage}
                </td>
              </tr>
            )}
            {!loading &&
              rows.map((row) => (
                <tr
                  key={rowKey(row)}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  className={`border-b border-hairline last:border-0 transition-colors duration-200 ${
                    onRowClick ? "cursor-pointer hover:bg-surface-elevated" : ""
                  }`}
                >
                  {columns.map((col) => (
                    <td key={col.key} className={`px-4 py-3 align-top text-ink ${col.className ?? ""}`}>
                      {col.render(row)}
                    </td>
                  ))}
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {pagination && (
        <div className="flex items-center justify-between border-t border-hairline px-4 py-3 text-xs text-ink-muted">
          <span>
            Menampilkan {pagination.total === 0 ? 0 : pagination.offset + 1}–
            {Math.min(pagination.offset + pagination.limit, pagination.total)} dari {pagination.total}
          </span>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              className="px-3 py-1.5 text-xs"
              disabled={pagination.offset === 0}
              onClick={() => pagination.onPageChange(Math.max(0, pagination.offset - pagination.limit))}
            >
              Sebelumnya
            </Button>
            <Button
              variant="secondary"
              className="px-3 py-1.5 text-xs"
              disabled={pagination.offset + pagination.limit >= pagination.total}
              onClick={() => pagination.onPageChange(pagination.offset + pagination.limit)}
            >
              Berikutnya
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
