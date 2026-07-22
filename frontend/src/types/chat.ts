import type { AttachmentReference, SourceReference } from "@/lib/apiClient"

export interface Message {
  role: "user" | "assistant"
  content: string
  timestamp: Date
  sources?: SourceReference[]
  attachments?: AttachmentReference[]
}
