import { http, HttpResponse, ws } from "msw"
import type {
  HealthResponse,
  ConversationsListResponse,
  ConversationDetail,
  MessagesListResponse,
  SendMessageResponse,
  RunsListResponse,
  RunDetail,
  ArtifactsListResponse,
  ArtifactDownloadResponse,
  GenomesListResponse,
  Conversation,
} from "@/lib/types"

const BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000") + "/api/v1"

const FIXTURE_CONVERSATIONS: Conversation[] = [
  {
    id: "conv-1",
    title: "RNA-seq bulk analysis",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T01:00:00Z",
  },
  {
    id: "conv-2",
    title: "Single-cell clustering",
    created_at: "2026-01-02T00:00:00Z",
    updated_at: "2026-01-02T02:00:00Z",
  },
]

const FIXTURE_RUN_COMPLETED: RunDetail = {
  id: "run-1",
  name: "bulk_rnaseq_run_1",
  status: "completed",
  pipeline_type: "bulk_rnaseq",
  conversation_id: "conv-1",
  triggering_message_id: "msg-1",
  created_at: "2026-01-01T00:00:00Z",
  started_at: "2026-01-01T00:01:00Z",
  completed_at: "2026-01-01T00:30:00Z",
  genome: { id: "genome-1", name: "GRCh38" },
  stages: [
    {
      id: "stage-1",
      stage_name: "fastqc",
      status: "completed",
      tool_name: "FastQC",
      started_at: "2026-01-01T00:01:00Z",
      completed_at: "2026-01-01T00:05:00Z",
      error_message: null,
    },
    {
      id: "stage-2",
      stage_name: "star_align",
      status: "completed",
      tool_name: "STAR",
      started_at: "2026-01-01T00:05:00Z",
      completed_at: "2026-01-01T00:25:00Z",
      error_message: null,
    },
  ],
  artifacts: [
    {
      id: "artifact-1",
      artifact_type: "fastqc_report",
      path: "s3://bucket/run-1/fastqc_report.html",
      file_size_bytes: 102400,
      created_at: "2026-01-01T00:05:00Z",
    },
  ],
}

const FIXTURE_RUN_RUNNING: RunDetail = {
  id: "run-2",
  name: "bulk_rnaseq_run_2",
  status: "running",
  pipeline_type: "bulk_rnaseq",
  conversation_id: "conv-1",
  triggering_message_id: "msg-2",
  created_at: "2026-01-02T00:00:00Z",
  started_at: "2026-01-02T00:01:00Z",
  completed_at: null,
  genome: { id: "genome-1", name: "GRCh38" },
  stages: [
    {
      id: "stage-3",
      stage_name: "fastqc",
      status: "completed",
      tool_name: "FastQC",
      started_at: "2026-01-02T00:01:00Z",
      completed_at: "2026-01-02T00:05:00Z",
      error_message: null,
    },
    {
      id: "stage-4",
      stage_name: "star_align",
      status: "running",
      tool_name: "STAR",
      started_at: "2026-01-02T00:05:00Z",
      completed_at: null,
      error_message: null,
    },
  ],
  artifacts: [],
}

export const handlers = [
  // Health
  http.get(`${BASE}/health`, () =>
    HttpResponse.json<HealthResponse>({ status: "ok", version: "0.1.0" })
  ),

  // Genomes
  http.get(`${BASE}/genomes`, () =>
    HttpResponse.json<GenomesListResponse>({
      genomes: [
        {
          id: "genome-1",
          name: "GRCh38",
          species: "Homo sapiens",
          assembly: "GRCh38",
          annotation: "Ensembl 109",
        },
        {
          id: "genome-2",
          name: "mm10",
          species: "Mus musculus",
          assembly: "mm10",
          annotation: "Ensembl 102",
        },
      ],
      total: 2,
      limit: 50,
      offset: 0,
    })
  ),

  // Conversations
  http.get(`${BASE}/conversations`, () =>
    HttpResponse.json<ConversationsListResponse>({
      conversations: FIXTURE_CONVERSATIONS,
      total: 2,
      limit: 50,
      offset: 0,
    })
  ),

  http.post(`${BASE}/conversations`, () =>
    HttpResponse.json<Conversation>(
      {
        id: "conv-new",
        title: "New conversation",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
      { status: 201 }
    )
  ),

  http.get(`${BASE}/conversations/:id`, ({ params }) =>
    HttpResponse.json<ConversationDetail>({
      id: params["id"] as string,
      title: "RNA-seq bulk analysis",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T01:00:00Z",
      message_count: 2,
    })
  ),

  http.get(`${BASE}/conversations/:id/messages`, () =>
    HttpResponse.json<MessagesListResponse>({
      messages: [
        {
          id: "msg-1",
          conversation_id: "conv-1",
          role: "user",
          content: "Run bulk RNA-seq on samples S1 and S2 using GRCh38.",
          run_id: null,
          tool_name: null,
          tool_status: null,
          created_at: "2026-01-01T00:00:00Z",
        },
        {
          id: "msg-2",
          conversation_id: "conv-1",
          role: "assistant",
          content: "Starting pipeline for samples S1 and S2.",
          run_id: "run-1",
          tool_name: null,
          tool_status: null,
          created_at: "2026-01-01T00:00:10Z",
        },
      ],
      total: 2,
      limit: 50,
      offset: 0,
    })
  ),

  http.post(`${BASE}/conversations/:id/messages`, () =>
    HttpResponse.json<SendMessageResponse>({
      message_id: "msg-new",
      run_id: null,
      status: "processing",
    })
  ),

  http.delete(`${BASE}/conversations/:id`, () => new HttpResponse(null, { status: 204 })),

  // Runs
  http.get(`${BASE}/runs`, () =>
    HttpResponse.json<RunsListResponse>({
      runs: [
        FIXTURE_RUN_COMPLETED,
        { ...FIXTURE_RUN_RUNNING, stages: undefined as never, artifacts: undefined as never },
      ],
      total: 2,
      limit: 50,
      offset: 0,
    })
  ),

  http.get(`${BASE}/runs/:id`, ({ params }) => {
    if (params["id"] === "run-2") return HttpResponse.json<RunDetail>(FIXTURE_RUN_RUNNING)
    return HttpResponse.json<RunDetail>(FIXTURE_RUN_COMPLETED)
  }),

  http.post(`${BASE}/runs/:id/cancel`, ({ params }) =>
    HttpResponse.json({ ...FIXTURE_RUN_COMPLETED, id: params["id"] as string, status: "cancelled" })
  ),

  // Artifacts
  http.get(`${BASE}/runs/:runId/artifacts`, () =>
    HttpResponse.json<ArtifactsListResponse>({
      artifacts: FIXTURE_RUN_COMPLETED.artifacts,
      total: 1,
    })
  ),

  http.get(`${BASE}/runs/:runId/artifacts/:artifactId/download`, () =>
    HttpResponse.json<ArtifactDownloadResponse>({
      download_url: "https://s3.example.com/presigned-url",
      expires_at: new Date(Date.now() + 3_600_000).toISOString(),
      file_name: "fastqc_report.html",
    })
  ),
]

// WebSocket mock links — used by the browser-side mock service worker.
// In Jest tests, WebSocket is mocked directly (msw WS interception is browser-only).
const WS_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
  /^http/,
  "ws"
)

export const conversationStreamLink = ws.link(
  `${WS_BASE}/ws/conversations/:id/stream`
)

export const runLogStreamLink = ws.link(`${WS_BASE}/ws/runs/:id/logs`)

/** Fixture handler: emits a token + done frame on every connection (browser dev mock). */
export const conversationStreamHandler = conversationStreamLink.addEventListener(
  "connection",
  ({ client }) => {
    client.send(
      JSON.stringify({
        type: "token",
        payload: { message_id: "fixture-msg", token: "Analysis complete. " },
      })
    )
    client.send(
      JSON.stringify({
        type: "done",
        payload: { message_id: "fixture-msg", run_id: null },
      })
    )
    client.close()
  }
)

export const runLogStreamHandler = runLogStreamLink.addEventListener(
  "connection",
  ({ client }) => {
    client.send(
      JSON.stringify({
        ts: new Date().toISOString(),
        level: "info",
        stage: "alignment",
        agent: "alignment_agent",
        message: "STAR alignment started for sample ctrl_1",
      })
    )
    client.close()
  }
)
