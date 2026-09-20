// API client. During development, Vite proxies these paths to the FastAPI
// backend (see vite.config.ts). All graph/GRACE endpoints live under /api.

import type {
  GraceResultDto,
  GraphView,
  IngestionSummary,
  LanguageStatus,
  ChatResponse,
  ForgeNode,
  ForgeEdge,
} from "./types";

export interface HealthResponse {
  status: string;
  version: string;
  llm_enabled: boolean;
}

/** Parse a JSON response, surfacing backend error detail when present. */
async function parseJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body && typeof body === "object" && "detail" in body) {
        const d = (body as { detail: unknown }).detail;
        detail = typeof d === "string" ? d : JSON.stringify(d);
      }
    } catch {
      // Non-JSON error body; keep the status line.
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export async function getHealth(): Promise<HealthResponse> {
  const res = await fetch("/health");
  return parseJson<HealthResponse>(res);
}

// ─── FORGE GRAPH API ────────────────────────────────────────────────────────
// Maps the Forge /graph/* shape into the existing GraphView type so GraphCanvas
// works without changes.

interface ForgeGraphView {
  nodes: ForgeNode[];
  edges: ForgeEdge[];
}

function forgeToGraphView(fv: ForgeGraphView): GraphView {
  return {
    nodes: fv.nodes.map((n) => ({
      id: n.id,
      label: n.label,
      level: n.type,           // Forge uses `type`, existing code uses `level`
      repoId: n.service ?? null,
      hasChildren: n.expandable,
    })),
    edges: fv.edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      kind: e.type,
      confidence: e.type === "HTTP_CALLS" ? 0.9 : null,
    })),
  };
}

/** Top-level view: service nodes + HTTP edges. Calls Forge /graph/overview. */
export async function getGraphTop(): Promise<GraphView> {
  const res = await fetch("/graph/overview");
  const fv = await parseJson<ForgeGraphView>(res);
  return forgeToGraphView(fv);
}

/**
 * Lazily fetch the one-hop children of a node.
 * Routes to /graph/service/{id} or /graph/symbol/{id} based on node id prefix.
 */
export async function expandNode(nodeId: string): Promise<GraphView> {
  let url: string;
  if (nodeId.startsWith("service:")) {
    const id = nodeId.replace("service:", "");
    url = `/graph/service/${encodeURIComponent(id)}`;
  } else {
    const id = nodeId.replace("symbol:", "");
    url = `/graph/symbol/${encodeURIComponent(id)}`;
  }
  const res = await fetch(url);
  const fv = await parseJson<ForgeGraphView>(res);
  return forgeToGraphView(fv);
}

// ─── FORGE IMPACT / CHAT API ─────────────────────────────────────────────────

/** Send a message (or start a session). Returns agent reply + session id. */
export async function sendChatMessage(
  message: string,
  sessionId?: string
): Promise<ChatResponse> {
  const res = await fetch("/impact/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId ?? null }),
  });
  return parseJson<ChatResponse>(res);
}

/** Clear a chat session. */
export async function deleteSession(sessionId: string): Promise<void> {
  await fetch(`/impact/chat/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  });
}

/** Get stats for the dashboard badge. */
export async function getGraphStats(): Promise<{
  services: number;
  symbols: number;
  edges: number;
}> {
  const res = await fetch("/graph/stats");
  const data = await parseJson<{
    nodes: { services: number; symbols: number; total: number };
    edges: { calls: number; http_calls: number; total: number };
  }>(res);
  return {
    services: data.nodes.services,
    symbols: data.nodes.symbols,
    edges: data.edges.total,
  };
}

// ─── LEGACY STUBS (kept so existing components compile) ─────────────────────

/** @deprecated Use sendChatMessage instead */
export async function runGraceQuery(
  question: string,
  _maxDepth?: number,
  _maxNodes?: number
): Promise<GraceResultDto> {
  // Re-route to impact/chat and shape the response into the legacy DTO.
  const chat = await sendChatMessage(question);
  return {
    nodes: [],
    edges: [],
    traversal_path: [],
    impacted_services: chat.impacted_services ?? [],
    serialized_context: "",
    llm_answer: chat.message,
    summary: chat.message,
  };
}

/** @deprecated Not used in Forge — ingest happens via code_graph/visualize_graph.py */
export async function ingestFolder(
  location: string,
  _repoName?: string
): Promise<IngestionSummary> {
  throw new Error(`Ingest not supported in Forge. Run visualize_graph.py on: ${location}`);
}

export async function ingestGit(
  location: string,
  _repoName?: string
): Promise<IngestionSummary> {
  throw new Error(`Ingest not supported in Forge. Run visualize_graph.py on: ${location}`);
}

export async function ingestZip(
  _file: File,
  _repoName?: string
): Promise<IngestionSummary> {
  throw new Error("Ingest not supported in Forge.");
}

export async function getLanguages(): Promise<{ languages: LanguageStatus[] }> {
  return { languages: [] };
}



// ─── PIPELINE API ────────────────────────────────────────────────────────────
// Multi-agent impact analysis pipeline endpoints

import type { PipelineState } from "./types";

/** Start a new pipeline with initial requirements. */
export async function startPipeline(message: string): Promise<PipelineState> {
  const res = await fetch("/pipeline/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  return parseJson<PipelineState>(res);
}

/** Respond to context gatherer questions. */
export async function respondToPipeline(
  pipelineId: string,
  message: string
): Promise<PipelineState> {
  const res = await fetch(`/pipeline/${encodeURIComponent(pipelineId)}/respond`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  return parseJson<PipelineState>(res);
}

/** Confirm requirements and start impact analysis. */
export async function confirmRequirements(pipelineId: string): Promise<PipelineState> {
  const res = await fetch(`/pipeline/${encodeURIComponent(pipelineId)}/confirm`, {
    method: "POST",
  });
  return parseJson<PipelineState>(res);
}

/** Get current pipeline status. */
export async function getPipelineStatus(pipelineId: string): Promise<PipelineState> {
  const res = await fetch(`/pipeline/${encodeURIComponent(pipelineId)}`);
  return parseJson<PipelineState>(res);
}

/** Approve or reject the pipeline results. */
export async function approvePipeline(
  pipelineId: string,
  approved: boolean,
  reason?: string
): Promise<PipelineState> {
  const res = await fetch(`/pipeline/${encodeURIComponent(pipelineId)}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approved, reason }),
  });
  return parseJson<PipelineState>(res);
}

/** Delete a pipeline session. */
export async function deletePipeline(pipelineId: string): Promise<void> {
  await fetch(`/pipeline/${encodeURIComponent(pipelineId)}`, {
    method: "DELETE",
  });
}


// ─── CODE GENERATION API ─────────────────────────────────────────────────────
// Multi-agent code generation endpoints

import type { CodeGenState, CodeGenPlan, AgentOutput, CodeGenResult } from "./types";

/** Start code generation from an approved pipeline. */
export async function startCodeGen(pipelineId: string): Promise<CodeGenState> {
  const res = await fetch("/codegen/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pipeline_id: pipelineId }),
  });
  return parseJson<CodeGenState>(res);
}

/** Get code generation status. */
export async function getCodeGenStatus(codegenId: string): Promise<CodeGenState> {
  const res = await fetch(`/codegen/${encodeURIComponent(codegenId)}`);
  return parseJson<CodeGenState>(res);
}

/** Get the generated plan. */
export async function getCodeGenPlan(codegenId: string): Promise<CodeGenPlan> {
  const res = await fetch(`/codegen/${encodeURIComponent(codegenId)}/plan`);
  return parseJson<CodeGenPlan>(res);
}

/** Get all generated diffs. */
export async function getCodeGenDiffs(codegenId: string): Promise<AgentOutput[]> {
  const res = await fetch(`/codegen/${encodeURIComponent(codegenId)}/diffs`);
  return parseJson<AgentOutput[]>(res);
}

/** Approve or reject generated code. */
export async function approveCodeGen(
  codegenId: string,
  approved: boolean,
  reason?: string
): Promise<CodeGenState> {
  const res = await fetch(`/codegen/${encodeURIComponent(codegenId)}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approved, reason }),
  });
  return parseJson<CodeGenState>(res);
}

/** Refine the plan with feedback. */
export async function refineCodeGen(
  codegenId: string,
  feedback: string
): Promise<CodeGenState> {
  const res = await fetch(`/codegen/${encodeURIComponent(codegenId)}/refine`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ feedback }),
  });
  return parseJson<CodeGenState>(res);
}

/** Get final result after approval. */
export async function getCodeGenResult(codegenId: string): Promise<CodeGenResult> {
  const res = await fetch(`/codegen/${encodeURIComponent(codegenId)}/result`);
  return parseJson<CodeGenResult>(res);
}

// ─── ENRICHMENT API ──────────────────────────────────────────────────────────

export interface PackageRow { package: string; version: string }
export interface PackagesData {
  by_service: Record<string, { runtime: PackageRow[]; dev: PackageRow[] }>;
  shared_packages: { package: string; used_by: string[] }[];
  total_entries: number;
}

export interface DbTablesData {
  by_service: Record<string, string[]>;
  total_tables: number;
}

export interface EndpointRow { method: string; path: string; operation_id: string }
export interface ApiEndpointsData {
  by_service: Record<string, EndpointRow[]>;
  total_endpoints: number;
}

export interface EnvVarsData {
  by_service: Record<string, string[]>;
  shared_vars: { env_var: string; used_by: string[] }[];
  total_entries: number;
}

export async function getPackages(service?: string): Promise<PackagesData> {
  const qs = service ? `?service=${encodeURIComponent(service)}` : "";
  const res = await fetch(`/graph/enrichment/packages${qs}`);
  return parseJson<PackagesData>(res);
}

export async function getDbTables(service?: string): Promise<DbTablesData> {
  const qs = service ? `?service=${encodeURIComponent(service)}` : "";
  const res = await fetch(`/graph/enrichment/db-tables${qs}`);
  return parseJson<DbTablesData>(res);
}

export async function getApiEndpoints(service?: string): Promise<ApiEndpointsData> {
  const qs = service ? `?service=${encodeURIComponent(service)}` : "";
  const res = await fetch(`/graph/enrichment/api-endpoints${qs}`);
  return parseJson<ApiEndpointsData>(res);
}

export async function getEnvVars(service?: string): Promise<EnvVarsData> {
  const qs = service ? `?service=${encodeURIComponent(service)}` : "";
  const res = await fetch(`/graph/enrichment/env-vars${qs}`);
  return parseJson<EnvVarsData>(res);
}
