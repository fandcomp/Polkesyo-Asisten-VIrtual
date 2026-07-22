/**
 * API client for backend communication.
 * Automatically attaches cookies and handles errors.
 */

interface ApiError {
  error?: string
  message?: string
}

interface SessionInitResponse {
  session_id: string
  created_at: string
  cookie_name: string
  cookie_value: string
}

interface ConsentResponse {
  id: string
  session_id: string
  consent_value: string
  created_at: string
}

interface ChatRequest {
  message: string
  metadata?: {
    source_page?: string
    page_url?: string
  }
  evaluation_mode?: boolean
  participant_code?: string
  scenario_code?: string
}

export interface SourceReference {
  document_title?: string
  document_id?: string
  section?: string
  page?: number
  chunk_id?: string
}

// Structure-aware document extraction plan — a downloadable form/attachment (.docx) linked
// to a cited document, only ever present when an admin has approved it (status === "active").
export interface AttachmentReference {
  form_title: string
  document_id: string
  download_url: string
}

export interface ChatResponse {
  answer: string
  sources: SourceReference[]
  attachments: AttachmentReference[]
  status: string
  session_id: string
  created_at: string
  trace_id?: string
  latency_ms?: number
  // Set when status === "needs_clarification"
  clarification_question?: string | null
}

/** Typed transport-level chat error carrying a user-displayable Indonesian message. */
export class ChatApiError extends Error {
  readonly status: number
  readonly errorType: string

  constructor(message: string, status: number, errorType: string = "unknown") {
    super(message)
    this.name = "ChatApiError"
    this.status = status
    this.errorType = errorType
  }
}

export interface HealthResponse {
  status: "ok" | "degraded"
  services: Record<string, "ok" | "error">
}

export interface AdminIdentityResponse {
  username: string
  /** null = unrestricted (primary admin); a list = only these Evaluation sub-tab keys are
   *  allowed (matches routes_evaluation_admin.py's require_evaluation_tab tags). */
  evaluation_tabs: string[] | null
}

export interface AdminDocumentResponse {
  id: string
  title: string
  type: string
  status: string
  created_at: string | null
  pending_chunk_count: number
  chunk_count: number
  latest_version_id: string | null
}

export interface IngestionResult {
  document_version_id?: string
  chunks_created?: number
  errors?: string[]
  status?: string
  error?: string
}

export interface AdminChunkResponse {
  id: string
  chunk_id: string
  chunk_index: number
  page: number | null
  section: string | null
  original_text: string
  status: string
  llm_summary: string | null
  admin_summary: string | null
  approved_summary: string | null
  risk_flags: string[]
  detected_entities: string[]
}

export interface DocumentChunksResponse {
  document_id: string
  chunks: AdminChunkResponse[]
  total: number
}

export type ChunkDecision = "approve" | "reject" | "needs_revision"

// Durable, per-chunk, admin-editable entity record (chunk_entities table).
export interface ChunkEntityResponse {
  id: string
  chunk_id: string
  document_id: string
  entity_type: string
  detected_text: string
  corrected_text: string | null
  corrected_type: string | null
  source: "llm_detected" | "admin_added"
  status: "detected" | "confirmed" | "edited" | "rejected"
  reviewed_by: string | null
  reviewed_at: string | null
  created_at: string | null
  updated_at: string | null
}

export interface ChunkEntitiesResponse {
  chunk_id: string
  entities: ChunkEntityResponse[]
}

export interface IndexingResult {
  status?: string
  indexed_count?: number
  skipped_count?: number
  errors?: string[]
  error?: string
}

export interface GraphIndexResult {
  status?: string
  created_nodes?: number
  created_relationships?: number
  errors?: string[]
  error?: string
}

export interface UploadDocumentResponse {
  document_id?: string
  version_id?: string
  filename?: string
  type?: string
  status?: string
  error?: string
  // Backend now runs extract->chunk->summarize (including vision extraction for PDFs)
  // synchronously as part of upload — no separate ingest call needed.
  ingestion?: IngestionResult | null
}

export interface VisualChunkBriefResponse {
  chunk_id: string
  page: number | null
  chunk_type: string
  image_hash: string | null
  raw_visual_description: string | null
  visible_text_draft: string | null
  uncertainty_notes: string | null
  risk_flags: string[]
  confidence_score: number | null
  admin_status: string
}

export interface VisualChunkPendingResponse {
  document_id: string
  total: number
  chunks: VisualChunkBriefResponse[]
}

export type VisualChunkDecision = "approve" | "reject" | "needs_revision"

// Structure-aware document extraction plan — admin review of generated form/attachment .docx.
export interface DocumentFormBriefResponse {
  form_id: string
  zone_type: "form_text" | "form_vision"
  form_title: string
  source_page_start: number
  source_page_end: number
  extraction_method: "text" | "vision"
  status: string
}

export interface DocumentFormPendingResponse {
  document_id: string
  total: number
  forms: DocumentFormBriefResponse[]
}

export type DocumentFormDecision = "approve" | "reject" | "needs_revision"

export interface KgNode {
  id: string
  label: string
  type: string
}

export interface KgEdge {
  source: string
  target: string
  type: string
}

export interface KgGraphResponse {
  nodes: KgNode[]
  edges: KgEdge[]
}

export interface DocumentSourceResponse {
  id: string
  source_name: string
  source_url: string
  source_type: string
  is_active: boolean
  last_checked_at: string | null
}

export interface AgentRunResponse {
  id: string
  agent_name: string
  task_type: string
  status: string
  latency_ms: number | null
  error_message: string | null
  input_summary: string | null
  output_summary: string | null
  created_at: string | null
}

export interface AdminScenarioResponse {
  id: string
  code: string
  title: string
  instruction: string
  expected_task: string | null
  order_index: number
  is_active: boolean
  created_at: string | null
}

export interface ScenarioCreatePayload {
  code: string
  title: string
  instruction: string
  expected_task?: string | null
  order_index?: number
  is_active?: boolean
}

export interface ScenarioUpdatePayload {
  title?: string
  instruction?: string
  expected_task?: string | null
  order_index?: number
  is_active?: boolean
}

export interface ChatEvaluationLogResponse {
  id: string
  trace_id: string
  session_id: string | null
  participant_code: string | null
  scenario_code: string | null
  evaluation_mode: boolean
  user_question: string
  final_answer: string | null
  fallback_triggered: boolean
  fallback_reason: string | null
  answer_status: string
  total_latency_ms: number | null
  retrieval_latency_ms: number | null
  graph_latency_ms: number | null
  acif_latency_ms: number | null
  llm_latency_ms: number | null
  output_verification_latency_ms: number | null
  model_used: string | null
  input_tokens: number | null
  output_tokens: number | null
  estimated_cost: number | null
  error_message: string | null
  created_at: string | null
}

export interface RetrievalEvaluationLogResponse {
  id: string
  trace_id: string
  chunk_id: string | null
  document_id: string | null
  document_version_id: string | null
  document_title: string | null
  page_number: number | null
  chunk_type: string | null
  retrieval_source: string
  retrieval_rank: number
  retrieval_score: number | null
  selected_for_context: boolean
  rejected_reason: string | null
  created_at: string | null
}

export interface CitationEvaluationLogResponse {
  id: string
  trace_id: string
  document_id: string | null
  chunk_id: string | null
  document_title: string | null
  page_number: number | null
  citation_type: string
  is_visual_source: boolean
  is_valid: boolean | null
  validation_notes: string | null
  created_at: string | null
}

export type AcifGateStatus = "pass" | "warn" | "block" | "fallback" | "error"

export interface AcifTraceLogResponse {
  id: string
  trace_id: string
  gate_number: number
  gate_name: string
  gate_status: AcifGateStatus
  risk_score: number | null
  risk_level: string | null
  action_taken: string | null
  risk_flags: Record<string, unknown> | null
  public_summary: string | null
  admin_summary: string | null
  latency_ms: number | null
  created_at: string | null
}

export interface PaginatedResponse<T> {
  total: number
  limit: number
  offset: number
  items: T[]
}

export interface ChatLogDetailResponse {
  chat_log: ChatEvaluationLogResponse
  retrieval: RetrievalEvaluationLogResponse[]
  citations: CitationEvaluationLogResponse[]
  acif_gates: AcifTraceLogResponse[]
  graph_consistency: Array<{
    id: string
    trace_id: string
    graph_entity: string | null
    graph_relation: string | null
    consistency_status: string
    notes: string | null
  }>
}

export interface ChatLogsQuery {
  dateFrom?: string
  dateTo?: string
  sessionId?: string
  participantCode?: string
  scenarioCode?: string
  fallbackTriggered?: boolean
  modelUsed?: string
  latencyMinMs?: number
  latencyMaxMs?: number
  limit?: number
  offset?: number
}

export interface EvaluationScenarioResponse {
  id: string
  code: string
  title: string
  instruction: string
  expected_task: string | null
  order_index: number
}

export interface AsqSubmission {
  participant_code: string
  scenario_code: string
  session_id?: string
  trace_id?: string
  asq_1: number
  asq_2: number
  asq_3: number
  notes?: string
}

export interface SusSubmission {
  participant_code: string
  session_id?: string
  sus_1: number
  sus_2: number
  sus_3: number
  sus_4: number
  sus_5: number
  sus_6: number
  sus_7: number
  sus_8: number
  sus_9: number
  sus_10: number
  notes?: string
}

export interface AsqResponseRecord {
  id: string
  participant_code: string
  scenario_code: string
  session_id: string | null
  trace_id: string | null
  asq_1: number
  asq_2: number
  asq_3: number
  average_score: number
  notes: string | null
  created_at: string | null
}

export interface AsqSummaryResponse {
  total_responses: number
  overall_average: number | null
  by_scenario: Array<{ scenario_code: string; average_score: number; count: number }>
  by_participant: Array<{ participant_code: string; average_score: number; count: number }>
  item_averages: { asq_1: number | null; asq_2: number | null; asq_3: number | null }
}

export interface SusResponseRecord {
  id: string
  participant_code: string
  session_id: string | null
  sus_1: number; sus_2: number; sus_3: number; sus_4: number; sus_5: number
  sus_6: number; sus_7: number; sus_8: number; sus_9: number; sus_10: number
  sus_score: number
  notes: string | null
  created_at: string | null
}

export interface SusSummaryResponse {
  total_responses: number
  overall_average: number | null
  by_participant: Array<{ participant_code: string; average_score: number; count: number }>
  item_averages: Record<string, number | null>
}

export interface EvaluationOverviewResponse {
  total_chat_logs: number
  average_latency_ms: number | null
  p95_latency_ms: number | null
  citation_coverage: number | null
  fallback_rate: number | null
  average_precision_at_3: number | null
  average_recall_at_3: number | null
  attack_success_rate: number | null
  average_asq_score: number | null
  average_sus_score: number | null
  acif_block_count: number
  acif_warning_count: number
}

export interface EvaluationRunResponse {
  id: string
  run_name: string
  config_name: string | null
  run_type: string
  total_questions: number
  completed_questions: number
  status: "pending" | "running" | "completed" | "failed" | "cancelled"
  started_at: string | null
  finished_at: string | null
  created_by: string | null
  notes: string | null
  created_at: string | null
}

export interface EvaluationResultResponse {
  id: string
  evaluation_run_id: string
  question_id: string
  trace_id: string | null
  category: string | null
  expected_behavior: string
  precision_at_3: number | null
  recall_at_3: number | null
  citation_present: boolean | null
  citation_correct: boolean | null
  fallback_correct: boolean | null
  attack_success: boolean | null
  answer_relevance_score: number | null
  faithfulness_score: number | null
  hallucination_detected: boolean | null
  total_latency_ms: number | null
  retrieval_latency_ms: number | null
  llm_latency_ms: number | null
  notes: string | null
  created_at: string | null
}

/** One metric's paired with/without-ACIF comparison (Evaluation Layer Phase 5) — mirrors
 *  statistical_comparison.py's MetricComparison. */
export interface MetricComparisonResponse {
  metric: string
  n_pairs: number
  mean_a: number | null
  mean_b: number | null
  mean_delta: number | null
  median_delta: number | null
  percent_change: number | null
  test_name: string
  statistic: number | null
  p_value: number | null
  significant: boolean | null
  note: string | null
}

export interface ComparisonReportResponse {
  run_id_a: string
  run_id_b: string
  config_name_a: string | null
  config_name_b: string | null
  n_paired_questions: number
  metrics: MetricComparisonResponse[]
  attack_success: MetricComparisonResponse | null
}

export interface GoldQaQuestionResponse {
  id: string
  category: string | null
  question: string
  expected_answer: string | null
  expected_document_ids: string[]
  expected_chunk_ids: string[]
  expected_pages: number[]
  expected_behavior: string
}

export interface StatsSummaryResponse {
  documents: {
    total: number
    by_status: Record<string, number>
  }
  chunks: {
    total: number
    by_status: Record<string, number>
    flagged: number
  }
  vector_index: {
    reachable: boolean
    count: number | null
    error?: string
  }
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"

const HEALTH_TIMEOUT_MS = 5000
const ADMIN_LOGIN_TIMEOUT_MS = 10000
// Above the backend's worst case (primary LLM 30s + fallback model + Gate 5 verify 20s)
const CHAT_TIMEOUT_MS = 75000

// The frontend and API live on different subdomains, so the browser's native Basic Auth
// popup — which only fires for top-level navigation, not background fetch/XHR — never
// appears for admin API calls made from the SPA. Storing the credentials here and
// attaching them explicitly to every /admin/* request replaces that broken flow with a
// real login form (see AdminAuthGate). sessionStorage, not localStorage: credentials
// clear when the tab closes rather than persisting indefinitely on disk.
const ADMIN_AUTH_STORAGE_KEY = "campus_va_admin_auth"

function getStoredAdminAuthHeader(): string | null {
  if (typeof window === "undefined") return null
  return window.sessionStorage.getItem(ADMIN_AUTH_STORAGE_KEY)
}

/** HTTP-level failure with the response status attached, so callers can tell an
 *  auth problem (401 — re-login) apart from an unreachable backend (network error). */
export class HttpError extends Error {
  constructor(
    message: string,
    readonly status: number
  ) {
    super(message)
    this.name = "HttpError"
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  if (path.startsWith("/admin") || path.startsWith("/api/admin")) {
    const adminAuth = getStoredAdminAuthHeader()
    if (adminAuth) headers.set("Authorization", adminAuth)
  }

  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    ...init,
    headers,
  })
  if (!res.ok) {
    let detail = ""
    try {
      const body = (await res.json()) as ApiError & { detail?: string }
      detail = body.detail ?? body.error ?? body.message ?? ""
    } catch {
      // response body was not JSON — keep the status-based message
    }
    throw new HttpError(detail || `Request failed: ${res.status} ${path}`, res.status)
  }
  return res.json() as Promise<T>
}

export class ApiClient {
  static hasAdminCredentials(): boolean {
    return getStoredAdminAuthHeader() !== null
  }

  static setAdminCredentials(username: string, password: string): void {
    window.sessionStorage.setItem(ADMIN_AUTH_STORAGE_KEY, `Basic ${btoa(`${username}:${password}`)}`)
  }

  static clearAdminCredentials(): void {
    window.sessionStorage.removeItem(ADMIN_AUTH_STORAGE_KEY)
  }

  /** Validates credentials against the backend before storing them — used by the admin login form.
   *  Bounded with a timeout so a slow/unresponsive backend fails fast instead of leaving the
   *  login form stuck on "Memeriksa..." forever. */
  static async verifyAdminCredentials(username: string, password: string): Promise<boolean> {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), ADMIN_LOGIN_TIMEOUT_MS)
    try {
      const res = await fetch(`${API_BASE}/admin/documents`, {
        credentials: "include",
        headers: { Authorization: `Basic ${btoa(`${username}:${password}`)}` },
        signal: controller.signal,
      })
      return res.ok
    } finally {
      clearTimeout(timeout)
    }
  }

  static async initSession(): Promise<SessionInitResponse> {
    const res = await fetch(`${API_BASE}/sessions/init`, {
      method: "POST",
      credentials: "include",
    })

    if (!res.ok) throw new Error("Failed to initialize session")
    return res.json()
  }

  static async setConsent(consentValue: string): Promise<ConsentResponse> {
    const res = await fetch(`${API_BASE}/consent/`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ consent_value: consentValue }),
    })

    if (!res.ok) throw new Error("Failed to set consent")
    return res.json()
  }

  /** Sends a chat message with a client-side deadline and friendly error mapping.
   *  The full pipeline (retrieval + LLM + verification) can legitimately take tens of
   *  seconds, so the timeout sits above the backend's own worst case (~60s) — it exists
   *  to stop an indefinitely-hung connection, not to race normal answers. */
  static async sendMessage(request: ChatRequest): Promise<ChatResponse> {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), CHAT_TIMEOUT_MS)
    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
        signal: controller.signal,
      })

      if (!res.ok) {
        let message = "Terjadi gangguan pada layanan. Silakan coba lagi beberapa saat."
        let errorType = "unknown"
        try {
          const body = (await res.json()) as { message?: string; detail?: string; error_type?: string }
          message = body.message ?? body.detail ?? message
          errorType = body.error_type ?? errorType
        } catch {
          // non-JSON error body — keep the generic copy
        }
        throw new ChatApiError(message, res.status, errorType)
      }
      return res.json()
    } catch (err) {
      if (err instanceof ChatApiError) throw err
      if (err instanceof DOMException && err.name === "AbortError") {
        throw new ChatApiError(
          "Respons membutuhkan waktu lebih lama dari biasanya. Silakan coba lagi beberapa saat.",
          0,
          "timeout",
        )
      }
      // fetch() network rejection (the browser's raw "Failed to fetch")
      throw new ChatApiError(
        "Tidak dapat terhubung ke server. Periksa koneksi Anda dan coba lagi.",
        0,
        "network_error",
      )
    } finally {
      clearTimeout(timeout)
    }
  }

  /** Recovers from a lost/unknown backend session without forcing a page reload:
   *  re-initializes the session, restores the consent choice from the client-side
   *  chat_consent cookie (the session cookie itself is HttpOnly and unreadable here),
   *  then retries the message once. Throws the retry's error if it also fails. */
  static async recoverSessionAndRetry(request: ChatRequest): Promise<ChatResponse> {
    await ApiClient.initSession()
    const consentMatch = document.cookie.match(/chat_consent=([^;]+)/)
    if (consentMatch) {
      await ApiClient.setConsent(consentMatch[1])
    }
    return ApiClient.sendMessage(request)
  }

  static async getHealth(): Promise<HealthResponse> {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS)
    try {
      return await requestJson<HealthResponse>("/health", { signal: controller.signal })
    } finally {
      clearTimeout(timeout)
    }
  }

  /** Which Evaluation sub-tabs the currently-authenticated admin can access — used to hide nav
   *  tabs a restricted (second) admin account can't use. UX only; the real enforcement is the
   *  backend's per-route 403. */
  static async getAdminIdentity(): Promise<AdminIdentityResponse> {
    return requestJson<AdminIdentityResponse>("/admin/me")
  }

  static async listDocuments(status?: string): Promise<AdminDocumentResponse[]> {
    const query = status ? `?status=${encodeURIComponent(status)}` : ""
    return requestJson<AdminDocumentResponse[]>(`/admin/documents${query}`)
  }

  /** Real aggregate counts (documents/chunks/flagged/vector-index size) for the monitoring
   *  dashboard — replaces client-side stat guessing that read a dead `Document.status`
   *  field and only counted chunks for whichever document was last opened. */
  static async getStatsSummary(): Promise<StatsSummaryResponse> {
    return requestJson<StatsSummaryResponse>("/admin/stats/summary")
  }

  static async getDocumentGraph(documentId: string): Promise<KgGraphResponse> {
    return requestJson<KgGraphResponse>(`/api/admin/kg/documents/${encodeURIComponent(documentId)}`)
  }

  static async getGlobalGraph(limit = 150): Promise<KgGraphResponse> {
    return requestJson<KgGraphResponse>(`/api/admin/kg/graph?limit=${limit}`)
  }

  static async listDocumentSources(): Promise<DocumentSourceResponse[]> {
    const res = await requestJson<{ total: number; sources: DocumentSourceResponse[] }>(
      "/admin/documents/sources"
    )
    return res.sources
  }

  static async listAgentRuns(agentName?: string, limit = 50): Promise<AgentRunResponse[]> {
    const params = new URLSearchParams({ limit: String(limit) })
    if (agentName) params.set("agent_name", agentName)
    const res = await requestJson<{ total: number; runs: AgentRunResponse[] }>(
      `/api/agent-runs?${params.toString()}`
    )
    return res.runs
  }

  static async getAgentRun(runId: string): Promise<AgentRunResponse> {
    return requestJson<AgentRunResponse>(`/api/agent-runs/${encodeURIComponent(runId)}`)
  }

  static async getDocumentChunks(documentId: string): Promise<DocumentChunksResponse> {
    return requestJson<DocumentChunksResponse>(
      `/admin/documents/${encodeURIComponent(documentId)}/chunks`
    )
  }

  static async updateChunkSummary(chunkId: string, approvedSummary: string): Promise<void> {
    await requestJson(`/admin/chunks/${encodeURIComponent(chunkId)}/summary`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approved_summary: approvedSummary }),
    })
  }

  static async decideChunk(chunkId: string, decision: ChunkDecision, notes = ""): Promise<void> {
    await requestJson(`/admin/chunks/${encodeURIComponent(chunkId)}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision, notes }),
    })
  }

  static async bulkApproveChunks(documentId: string): Promise<{ chunks_approved: number }> {
    return requestJson<{ chunks_approved: number }>(
      `/admin/chunks/bulk-approve?document_id=${encodeURIComponent(documentId)}`,
      { method: "POST" }
    )
  }

  /** Single source of truth for the entity-type vocabulary — mirrors
   *  GraphService.ALLOWED_ENTITY_TYPES so the frontend's type dropdown never drifts. */
  static async getEntityTypes(): Promise<string[]> {
    const res = await requestJson<{ entity_types: string[] }>("/admin/entity-types")
    return res.entity_types
  }

  /** Lists a chunk's durable entity records, materializing the detected list server-side
   *  on first access (mirrors listPendingVisualChunks' lazy-fetch-per-chunk pattern). */
  static async getChunkEntities(chunkId: string): Promise<ChunkEntitiesResponse> {
    return requestJson<ChunkEntitiesResponse>(
      `/admin/chunks/${encodeURIComponent(chunkId)}/entities`
    )
  }

  static async editChunkEntity(
    chunkId: string,
    entityId: string,
    correction: { correctedText?: string; correctedType?: string }
  ): Promise<ChunkEntityResponse> {
    return requestJson<ChunkEntityResponse>(
      `/admin/chunks/${encodeURIComponent(chunkId)}/entities/${encodeURIComponent(entityId)}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          corrected_text: correction.correctedText,
          corrected_type: correction.correctedType,
        }),
      }
    )
  }

  static async confirmChunkEntity(chunkId: string, entityId: string): Promise<ChunkEntityResponse> {
    return requestJson<ChunkEntityResponse>(
      `/admin/chunks/${encodeURIComponent(chunkId)}/entities/${encodeURIComponent(entityId)}/confirm`,
      { method: "POST" }
    )
  }

  /** The only "delete" mechanism for a chunk entity — never hard-deleted (audit trail). */
  static async rejectChunkEntity(chunkId: string, entityId: string): Promise<ChunkEntityResponse> {
    return requestJson<ChunkEntityResponse>(
      `/admin/chunks/${encodeURIComponent(chunkId)}/entities/${encodeURIComponent(entityId)}/reject`,
      { method: "POST" }
    )
  }

  static async addChunkEntity(
    chunkId: string,
    entityType: string,
    text: string
  ): Promise<ChunkEntityResponse> {
    return requestJson<ChunkEntityResponse>(
      `/admin/chunks/${encodeURIComponent(chunkId)}/entities`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ entity_type: entityType, text }),
      }
    )
  }

  static async runIndexing(documentId?: string): Promise<IndexingResult> {
    const query = documentId ? `?document_id=${encodeURIComponent(documentId)}` : ""
    return requestJson<IndexingResult>(`/admin/indexing/run${query}`, { method: "POST" })
  }

  static async indexDocumentGraph(documentId: string): Promise<GraphIndexResult> {
    return requestJson<GraphIndexResult>(
      `/admin/graph/index-document?document_id=${encodeURIComponent(documentId)}`,
      { method: "POST" }
    )
  }

  static async ingestDocument(versionId: string): Promise<IngestionResult> {
    return requestJson<IngestionResult>(
      `/admin/ingestion/ingest-document/${encodeURIComponent(versionId)}`,
      { method: "POST" }
    )
  }

  static async uploadDocument(
    file: File,
    title: string,
    documentType?: string
  ): Promise<UploadDocumentResponse> {
    const formData = new FormData()
    formData.append("file", file)
    // `title`/`document_type` are query parameters on the backend, not form fields
    const params = new URLSearchParams()
    if (title) params.set("title", title)
    if (documentType) params.set("document_type", documentType)
    const query = params.toString() ? `?${params.toString()}` : ""
    const result = await requestJson<UploadDocumentResponse>(
      `/admin/documents/upload${query}`,
      { method: "POST", body: formData }
    )
    if (result.error) throw new Error(result.error)
    return result
  }

  static async listPendingVisualChunks(documentId: string): Promise<VisualChunkPendingResponse> {
    return requestJson<VisualChunkPendingResponse>(
      `/admin/visual-chunks/${encodeURIComponent(documentId)}/pending`
    )
  }

  static getVisualChunkImageUrl(chunkId: string): string {
    return `${API_BASE}/admin/visual-chunks/${encodeURIComponent(chunkId)}/image`
  }

  /** Fetches the visual chunk's image with the admin Basic Auth header attached and
   *  returns a local object URL. A plain <img src={getVisualChunkImageUrl(...)}> cannot
   *  carry that header (browsers never attach custom headers to <img>/<a> requests), so
   *  every preview and "open full size" link was silently getting a 401 and rendering
   *  nothing — same root cause downloadEvaluationExport already works around for CSV. */
  static async getVisualChunkImageBlobUrl(chunkId: string): Promise<string> {
    const headers = new Headers()
    const adminAuth = getStoredAdminAuthHeader()
    if (adminAuth) headers.set("Authorization", adminAuth)

    const res = await fetch(ApiClient.getVisualChunkImageUrl(chunkId), { credentials: "include", headers })
    if (!res.ok) throw new Error(`Gagal memuat gambar (${res.status})`)

    const blob = await res.blob()
    return URL.createObjectURL(blob)
  }

  static getDocumentDownloadUrl(documentId: string): string {
    return `${API_BASE}/documents/${encodeURIComponent(documentId)}/download`
  }

  static async listChatLogs(query: ChatLogsQuery = {}): Promise<PaginatedResponse<ChatEvaluationLogResponse>> {
    const params = new URLSearchParams()
    if (query.dateFrom) params.set("date_from", query.dateFrom)
    if (query.dateTo) params.set("date_to", query.dateTo)
    if (query.sessionId) params.set("session_id", query.sessionId)
    if (query.participantCode) params.set("participant_code", query.participantCode)
    if (query.scenarioCode) params.set("scenario_code", query.scenarioCode)
    if (query.fallbackTriggered !== undefined) params.set("fallback_triggered", String(query.fallbackTriggered))
    if (query.modelUsed) params.set("model_used", query.modelUsed)
    if (query.latencyMinMs !== undefined) params.set("latency_min_ms", String(query.latencyMinMs))
    if (query.latencyMaxMs !== undefined) params.set("latency_max_ms", String(query.latencyMaxMs))
    params.set("limit", String(query.limit ?? 50))
    params.set("offset", String(query.offset ?? 0))
    return requestJson<PaginatedResponse<ChatEvaluationLogResponse>>(
      `/api/admin/evaluation/chat-logs?${params.toString()}`
    )
  }

  static async getChatLogDetail(traceId: string): Promise<ChatLogDetailResponse> {
    return requestJson<ChatLogDetailResponse>(
      `/api/admin/evaluation/chat-logs/${encodeURIComponent(traceId)}`
    )
  }

  static async listRetrievalLogs(params: {
    traceId?: string
    documentId?: string
    limit?: number
    offset?: number
  } = {}): Promise<PaginatedResponse<RetrievalEvaluationLogResponse>> {
    const q = new URLSearchParams()
    if (params.traceId) q.set("trace_id", params.traceId)
    if (params.documentId) q.set("document_id", params.documentId)
    q.set("limit", String(params.limit ?? 50))
    q.set("offset", String(params.offset ?? 0))
    return requestJson<PaginatedResponse<RetrievalEvaluationLogResponse>>(
      `/api/admin/evaluation/retrieval-logs?${q.toString()}`
    )
  }

  static async listCitationLogs(params: {
    traceId?: string
    documentId?: string
    isValid?: boolean
    limit?: number
    offset?: number
  } = {}): Promise<PaginatedResponse<CitationEvaluationLogResponse>> {
    const q = new URLSearchParams()
    if (params.traceId) q.set("trace_id", params.traceId)
    if (params.documentId) q.set("document_id", params.documentId)
    if (params.isValid !== undefined) q.set("is_valid", String(params.isValid))
    q.set("limit", String(params.limit ?? 50))
    q.set("offset", String(params.offset ?? 0))
    return requestJson<PaginatedResponse<CitationEvaluationLogResponse>>(
      `/api/admin/evaluation/citation-logs?${q.toString()}`
    )
  }

  static async listAcifTraces(params: {
    gateStatus?: AcifGateStatus
    gateName?: string
    riskLevel?: string
    limit?: number
    offset?: number
  } = {}): Promise<PaginatedResponse<AcifTraceLogResponse>> {
    const q = new URLSearchParams()
    if (params.gateStatus) q.set("gate_status", params.gateStatus)
    if (params.gateName) q.set("gate_name", params.gateName)
    if (params.riskLevel) q.set("risk_level", params.riskLevel)
    q.set("limit", String(params.limit ?? 50))
    q.set("offset", String(params.offset ?? 0))
    return requestJson<PaginatedResponse<AcifTraceLogResponse>>(
      `/api/admin/evaluation/acif-traces?${q.toString()}`
    )
  }

  static async getAcifTraceDetail(traceId: string): Promise<{ trace_id: string; gates: AcifTraceLogResponse[] }> {
    return requestJson(`/api/admin/evaluation/acif-traces/${encodeURIComponent(traceId)}`)
  }

  static async listEvaluationScenarios(): Promise<EvaluationScenarioResponse[]> {
    const res = await requestJson<{ scenarios: EvaluationScenarioResponse[] }>("/api/evaluation/scenarios")
    return res.scenarios
  }

  /** Admin variant — includes inactive scenarios, unlike the public read-only endpoint above. */
  static async listEvaluationScenariosAdmin(): Promise<AdminScenarioResponse[]> {
    const res = await requestJson<{ scenarios: AdminScenarioResponse[] }>(
      "/api/admin/evaluation/scenarios"
    )
    return res.scenarios
  }

  static async createEvaluationScenario(payload: ScenarioCreatePayload): Promise<AdminScenarioResponse> {
    return requestJson<AdminScenarioResponse>("/api/admin/evaluation/scenarios", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
  }

  static async updateEvaluationScenario(
    scenarioId: string,
    payload: ScenarioUpdatePayload
  ): Promise<AdminScenarioResponse> {
    return requestJson<AdminScenarioResponse>(
      `/api/admin/evaluation/scenarios/${encodeURIComponent(scenarioId)}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }
    )
  }

  static async submitAsq(submission: AsqSubmission): Promise<{ id: string; average_score: number }> {
    return requestJson("/api/evaluation/asq", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(submission),
    })
  }

  static async submitSus(submission: SusSubmission): Promise<{ id: string; sus_score: number }> {
    return requestJson("/api/evaluation/sus", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(submission),
    })
  }

  static async getAsqSummary(): Promise<AsqSummaryResponse> {
    return requestJson("/api/admin/evaluation/asq-summary")
  }

  static async listAsqResponses(params: { limit?: number; offset?: number } = {}): Promise<
    PaginatedResponse<AsqResponseRecord>
  > {
    const q = new URLSearchParams()
    q.set("limit", String(params.limit ?? 50))
    q.set("offset", String(params.offset ?? 0))
    return requestJson(`/api/admin/evaluation/asq-responses?${q.toString()}`)
  }

  static async getSusSummary(): Promise<SusSummaryResponse> {
    return requestJson("/api/admin/evaluation/sus-summary")
  }

  static async listSusResponses(params: { limit?: number; offset?: number } = {}): Promise<
    PaginatedResponse<SusResponseRecord>
  > {
    const q = new URLSearchParams()
    q.set("limit", String(params.limit ?? 50))
    q.set("offset", String(params.offset ?? 0))
    return requestJson(`/api/admin/evaluation/sus-responses?${q.toString()}`)
  }

  static async getEvaluationOverview(): Promise<EvaluationOverviewResponse> {
    return requestJson("/api/admin/evaluation/overview")
  }

  static async listEvaluationRuns(params: { limit?: number; offset?: number } = {}): Promise<
    PaginatedResponse<EvaluationRunResponse>
  > {
    const q = new URLSearchParams()
    q.set("limit", String(params.limit ?? 20))
    q.set("offset", String(params.offset ?? 0))
    return requestJson(`/api/admin/evaluation/runs?${q.toString()}`)
  }

  static async triggerEvaluationRun(
    runName: string,
    options?: { configName?: string; ablationDisableAcif?: boolean }
  ): Promise<{ status: string; run_name: string; config_name: string }> {
    return requestJson("/api/admin/evaluation/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        run_name: runName,
        config_name: options?.configName ?? "with_acif",
        ablation_disable_acif: options?.ablationDisableAcif ?? false,
      }),
    })
  }

  static async getEvaluationRunDetail(
    runId: string
  ): Promise<{ run: EvaluationRunResponse; results: EvaluationResultResponse[] }> {
    return requestJson(`/api/admin/evaluation/runs/${encodeURIComponent(runId)}`)
  }

  /** Paired with/without-ACIF statistical comparison between two evaluation_runs
   *  (Evaluation Layer Phase 5) — the thesis rumusan masalah endpoint. */
  static async compareEvaluationRuns(runIdA: string, runIdB: string): Promise<ComparisonReportResponse> {
    const q = new URLSearchParams({ run_id_a: runIdA, run_id_b: runIdB })
    return requestJson(`/api/admin/evaluation/compare?${q.toString()}`)
  }

  static async getGoldQaDataset(): Promise<Record<string, GoldQaQuestionResponse>> {
    const res = await requestJson<{ questions: Record<string, GoldQaQuestionResponse> }>(
      "/api/admin/evaluation/gold-qa-dataset"
    )
    return res.questions
  }

  /** Downloads an evaluation CSV export and triggers a browser save-as. A plain <a href>
   *  can't carry the admin Basic Auth header the export endpoint requires, so this fetches
   *  the CSV as a Blob (with the same auth header requestJson attaches) and saves it via a
   *  throwaway object URL — kept out of requestJson since the response here is CSV, not JSON. */
  static async downloadEvaluationExport(
    kind: "chat-logs" | "retrieval" | "citations" | "acif" | "asq" | "sus" | "combined-report" | "compare",
    params: Record<string, string> = {},
    filename: string
  ): Promise<void> {
    const q = new URLSearchParams(params)
    const query = q.toString() ? `?${q.toString()}` : ""
    const path = `/api/admin/evaluation/export/${kind}.csv${query}`

    const headers = new Headers()
    const adminAuth = getStoredAdminAuthHeader()
    if (adminAuth) headers.set("Authorization", adminAuth)

    const res = await fetch(`${API_BASE}${path}`, { credentials: "include", headers })
    if (!res.ok) throw new Error(`Export failed: ${res.status}`)

    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement("a")
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }

  static async decideVisualChunk(
    chunkId: string,
    decision: VisualChunkDecision,
    options?: { editedSummary?: string; reason?: string }
  ): Promise<void> {
    const params = new URLSearchParams()
    if (decision === "approve" || decision === "needs_revision") {
      // Both approve and needs_revision let the admin persist an in-progress fix to the
      // visual description; reject does not need one since the chunk is discarded.
      if (options?.editedSummary) params.set("edited_summary", options.editedSummary)
    }
    if (options?.reason) {
      params.set(decision === "approve" ? "admin_notes" : "reason", options.reason)
    }
    const query = params.toString() ? `?${params.toString()}` : ""
    const path =
      decision === "needs_revision"
        ? `/admin/visual-chunks/${encodeURIComponent(chunkId)}/needs-revision`
        : `/admin/visual-chunks/${encodeURIComponent(chunkId)}/${decision}`
    await requestJson(`${path}${query}`, { method: "POST" })
  }

  // Structure-aware document extraction plan — admin review of generated form/attachment .docx.

  static async listPendingDocumentForms(documentId: string): Promise<DocumentFormPendingResponse> {
    return requestJson<DocumentFormPendingResponse>(
      `/admin/document-forms/${encodeURIComponent(documentId)}/pending`
    )
  }

  static getDocumentFormDownloadUrl(formId: string): string {
    return `${API_BASE}/admin/document-forms/${encodeURIComponent(formId)}/download`
  }

  /** Same admin-Basic-Auth-header workaround as getVisualChunkImageBlobUrl: a plain <a href>
   *  cannot carry the Authorization header, so this fetches the .docx with it attached and
   *  hands back a local object URL to download/open instead. */
  static async getDocumentFormDownloadBlobUrl(formId: string): Promise<string> {
    const headers = new Headers()
    const adminAuth = getStoredAdminAuthHeader()
    if (adminAuth) headers.set("Authorization", adminAuth)

    const res = await fetch(ApiClient.getDocumentFormDownloadUrl(formId), { credentials: "include", headers })
    if (!res.ok) throw new Error(`Gagal memuat formulir (${res.status})`)

    const blob = await res.blob()
    return URL.createObjectURL(blob)
  }

  static async decideDocumentForm(
    formId: string,
    decision: DocumentFormDecision,
    options?: { adminNotes?: string; reason?: string }
  ): Promise<void> {
    const params = new URLSearchParams()
    if (decision === "approve" && options?.adminNotes) params.set("admin_notes", options.adminNotes)
    if (decision !== "approve" && options?.reason) params.set("reason", options.reason)
    const query = params.toString() ? `?${params.toString()}` : ""
    const path =
      decision === "needs_revision"
        ? `/admin/document-forms/${encodeURIComponent(formId)}/needs-revision`
        : `/admin/document-forms/${encodeURIComponent(formId)}/${decision}`
    await requestJson(`${path}${query}`, { method: "POST" })
  }

  /** Public download link for a chat attachment (AttachmentReference.download_url is already
   *  a relative path like "/documents/{id}/forms/{formId}/download") — no admin auth needed,
   *  same as getDocumentDownloadUrl. */
  static getPublicFormDownloadUrl(downloadUrl: string): string {
    return `${API_BASE}${downloadUrl}`
  }
}
