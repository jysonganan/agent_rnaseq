// All TypeScript interfaces mirroring docs/specs/api_contracts.md

export type RunStatus = "pending" | "running" | "completed" | "failed" | "cancelled"
export type StageStatus = "pending" | "running" | "completed" | "failed" | "skipped"
export type MessageRole = "user" | "assistant" | "tool"

// RFC 9457 Problem Details
export interface ApiProblemDetail {
  type: string
  title: string
  status: number
  detail: string
  instance?: string
}

// Health
export interface HealthResponse {
  status: string
  version: string
}

// Genomes
export interface Genome {
  id: string
  name: string
  species: string
  assembly: string
  annotation: string
}

export interface GenomesListResponse {
  genomes: Genome[]
  total: number
  limit: number
  offset: number
}

// Projects
export interface Project {
  id: string
  name: string
  description: string | null
  created_at: string
}

export interface Sample {
  id: string
  project_id: string
  name: string
  condition: string
  fastq_r1_path: string
  fastq_r2_path: string | null
  created_at: string
}

export interface ProjectDetail extends Project {
  samples: Sample[]
}

export interface ProjectsListResponse {
  projects: Project[]
  total: number
  limit: number
  offset: number
}

// Runs
export interface Stage {
  id: string
  stage_name: string
  status: StageStatus
  tool_name: string
  started_at: string | null
  completed_at: string | null
  error_message: string | null
}

export interface Artifact {
  id: string
  artifact_type: string
  path: string
  file_size_bytes: number | null
  created_at: string
}

export interface Run {
  id: string
  name: string
  status: RunStatus
  pipeline_type: string
  conversation_id: string | null
  triggering_message_id: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
}

export interface RunDetail extends Run {
  genome: { id: string; name: string }
  stages: Stage[]
  artifacts: Artifact[]
}

export interface RunsListResponse {
  runs: Run[]
  total: number
  limit: number
  offset: number
}

export interface ArtifactDownloadResponse {
  download_url: string
  expires_at: string
  file_name: string
}

export interface ArtifactsListResponse {
  artifacts: Artifact[]
  total: number
}

// Conversations
export interface Conversation {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface ConversationDetail extends Conversation {
  message_count: number
}

export interface ConversationsListResponse {
  conversations: Conversation[]
  total: number
  limit: number
  offset: number
}

export interface ChatMessage {
  id: string
  conversation_id: string
  role: MessageRole
  content: string
  run_id: string | null
  tool_name: string | null
  tool_status: string | null
  created_at: string
}

export interface MessagesListResponse {
  messages: ChatMessage[]
  total: number
  limit: number
  offset: number
}

export interface SendMessageResponse {
  message_id: string
  run_id: string | null
  status: "processing" | "complete"
}

// WebSocket frame status
export type WsStatus = "connecting" | "connected" | "error"

// WebSocket payload types (payload-wrapped format from server)
export type WsFrameType = "token" | "tool_call" | "stage_update" | "done" | "error"

export interface TokenPayload {
  message_id: string
  token: string
}

export interface ToolCallPayload {
  message_id: string
  tool_name: string
  status: string
  summary: string | null
}

export interface StageUpdatePayload {
  run_id: string
  stage_name: string
  status: string
}

export interface DonePayload {
  message_id: string
  run_id: string | null
}

export interface WsErrorPayload {
  message: string
}

export interface WsFrame {
  type: WsFrameType
  payload: TokenPayload | ToolCallPayload | StageUpdatePayload | DonePayload | WsErrorPayload
}

// Run log frame (flat format from WS /ws/runs/{id}/logs)
export interface RunLogFrame {
  ts: string
  level: "info" | "warning" | "error" | "debug"
  stage: string
  agent: string
  message: string
}

// Legacy flat stream frames (kept for backwards compat)
export interface TokenFrame {
  type: "token"
  delta: string
}

export interface ToolCallFrame {
  type: "tool_call"
  tool_name: string
  summary: string
  run_id: string | null
}

export interface StageUpdateFrame {
  type: "stage_update"
  stage: Stage
}

export interface DoneFrame {
  type: "done"
  run_id: string | null
  message_id: string
}

export interface ErrorFrame {
  type: "error"
  code: string
  message: string
}

export type ConversationStreamFrame =
  | TokenFrame
  | ToolCallFrame
  | StageUpdateFrame
  | DoneFrame
  | ErrorFrame

// QC Metrics
export interface QCMetrics {
  run_id: string
  total_reads: number
  mapped_reads: number
  mapping_rate: number
  median_insert_size: number | null
  pct_duplication: number | null
}

// DE Results
export interface DEResult {
  gene_id: string
  gene_name: string
  baseMean: number
  log2FoldChange: number
  pvalue: number
  padj: number
}

export interface DEResultsResponse {
  run_id: string
  contrast: string
  results: DEResult[]
  total: number
}

// GSEA
export interface GSEAPathway {
  pathway: string
  NES: number
  pval: number
  padj: number
  size: number
}

export interface GSEAResultsResponse {
  run_id: string
  pathways: GSEAPathway[]
  total: number
}

// API Keys
export interface ApiKeyInfo {
  id: string
  name: string
  key_prefix: string
  created_at: string
  last_used_at: string | null
}

export interface ApiKeysListResponse {
  api_keys: ApiKeyInfo[]
}

export interface CreateApiKeyResponse {
  id: string
  name: string
  key: string
  created_at: string
}
