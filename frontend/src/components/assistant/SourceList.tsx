import { ApiClient, type AttachmentReference, type SourceReference } from "@/lib/apiClient"

interface SourceListProps {
  sources: SourceReference[]
  attachments?: AttachmentReference[]
}

export function SourceList({ sources, attachments = [] }: SourceListProps) {
  if (sources.length === 0 && attachments.length === 0) return null

  return (
    <div className="mt-2 flex flex-col gap-1 border-t border-hairline pt-2">
      {sources.map((source, idx) => {
        const label = (
          <>
            {source.document_title ?? "Dokumen resmi"}
            {source.section ? `, ${source.section}` : ""}
            {source.page ? `, hal. ${source.page}` : ""}
          </>
        )

        return (
          <p key={idx} className="text-xs text-ink-muted">
            <span className="font-medium text-primary">Sumber:</span>{" "}
            {source.document_id ? (
              <a
                href={ApiClient.getDocumentDownloadUrl(source.document_id)}
                className="underline decoration-dotted underline-offset-2 hover:text-primary"
                target="_blank"
                rel="noopener noreferrer"
              >
                {label}
              </a>
            ) : (
              label
            )}
          </p>
        )
      })}
      {attachments.map((attachment, idx) => (
        <p key={`attachment-${idx}`} className="text-xs text-ink-muted">
          <span className="font-medium text-primary">Formulir:</span>{" "}
          <a
            href={ApiClient.getPublicFormDownloadUrl(attachment.download_url)}
            className="underline decoration-dotted underline-offset-2 hover:text-primary"
            target="_blank"
            rel="noopener noreferrer"
          >
            {attachment.form_title} (unduh .docx)
          </a>
        </p>
      ))}
    </div>
  )
}
