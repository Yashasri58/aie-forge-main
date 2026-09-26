// Shared graph DTO types. These match the backend wire shapes exactly
// (see backend/app/api/dtos.py). The frontend renders every node/edge
// uniformly regardless of which endpoint produced it, so /graph/top,
// /graph/expand and /grace/query all speak these types.

// Coarse frontend level. The backend maps internal node kinds onto this set
// (service | file | function | identifier | topic | route). We keep the string
// open-ended defensively but the known values drive styling.
export type NodeLevel =
  | "service"
  | "file"
  | "function"
  | "identifier"
  | "topic"
  | "route";

export interface GraphNode {
  id: string;
  label: string;
  level: NodeLevel | string;
  repoId?: string | null;
  hasChildren: boolean;
}

// Known edge kinds. SERVICE edges (HTTP_CALLS / PUBLISHES_TO / SUBSCRIBES_TO)
// carry a numeric confidence; exact CODE edges leave confidence null/undefined.
export type EdgeKind =
  | "DEFINES"
  | "REFERENCES"
  | "CALLS"
  | "IMPORTS"
  | "DEFINES_ROUTE"
  | "HTTP_CALLS"
  | "PUBLISHES_TO"
  | "SUBSCRIBES_TO";

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  kind: EdgeKind | string;
  confidence?: number | null;
}

export interface GraphView {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

// --- Ingestion summary (rendered defensively; exact fields may vary) --------

export interface LanguageStatus {
  language: string;
  tested: boolean;
  available: boolean;
  status?: string;
  detail?: string;
}

export interface IngestedRepoSummary {
  repo_id: string;
  repo_name: string;
  detected_languages: string[];
  languages: LanguageStatus[];
}

export interface IngestionSummary {
  repos: IngestedRepoSummary[];
  node_count: number;
  edge_count: number;
  service_edge_count: number;
}

// --- GRACE (Task 10 consumes this; typed here so the api method is ready) ---

export interface GraceResultDto {
  nodes: GraphNode[];
  edges: GraphEdge[];
  traversal_path: string[];
  impacted_services: string[];
  serialized_context: string;
  llm_answer: string | null;
  // Deterministic, human-readable structural summary. Shown when there is no
  // LLM answer (falls back to serialized_context only if this is empty).
  summary?: string;
}

// --- Edge classification helpers (shared styling logic) ---------------------

// SERVICE (inferred) edge kinds carry confidence; everything else is exact CODE.
export const SERVICE_EDGE_KINDS: ReadonlySet<string> = new Set([
  "HTTP_CALLS",
  "PUBLISHES_TO",
  "SUBSCRIBES_TO",
]);

/** True when an edge is an inferred SERVICE edge (has a numeric confidence). */
export function isServiceEdge(edge: GraphEdge): boolean {
  return (
    SERVICE_EDGE_KINDS.has(edge.kind) ||
    (edge.confidence !== null && edge.confidence !== undefined)
  );
}

// ─── FORGE API TYPES ─────────────────────────────────────────────────────────
// These match the Forge FastAPI backend wire shapes exactly.

/** Node shape returned by /graph/overview, /graph/service/*, /graph/symbol/* */
export interface ForgeNode {
  id: string;
  label: string;
  type: "service" | "function" | "class" | "method" | "other";
  expandable: boolean;
  child_count?: number;
  service?: string;
  file?: string;
  kind?: string;
}

/** Edge shape returned by Forge graph endpoints */
export interface ForgeEdge {
  id: string;
  source: string;
  target: string;
  type: string;
}

/** Single chat message */
export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

/** Response from POST /impact/chat */
export interface ChatResponse {
  session_id: string;
  message: string;
  history: ChatMessage[];
  impacted_services: string[] | null;
}

/** Graph stats from GET /graph/stats */
export interface GraphStats {
  services: number;
  symbols: number;
  edges: number;
}



// ─── PIPELINE API TYPES ──────────────────────────────────────────────────────
// Types for the multi-agent impact analysis pipeline

export type PipelineStage = 
  | "gathering"
  | "requirements_ready"
  | "analyzing"
  | "verifying"
  | "filling_gaps"
  | "scoring"
  | "planning"
  | "chain_analysis"
  | "awaiting_approval"
  | "approved"
  | "rejected"
  | "failed";

export interface PipelineRequirements {
  title?: string;
  description?: string;
  services?: string[];
  functions?: string[];
  files?: string[];
  scope?: {
    services?: string[];
    functions?: string[];
    files?: string[];
  };
  change_type?: "feature" | "bugfix" | "refactor" | "migration" | "add_feature" | "unknown";
  constraints?: string[];
  clarity_score?: number;
  complete?: boolean;
  follow_up_question?: string | null;
}

export interface ScoredImpact {
  name: string;
  type: "service" | "file" | "function";
  risk_level: "HIGH" | "MEDIUM" | "LOW";
  risk_factors: string[];
  mitigation: string;
}

export interface BlastRadius {
  services_affected: number;
  total_services: number;
  percentage: number;
  assessment: "CRITICAL" | "HIGH" | "MODERATE" | "LOW" | "NONE";
}

export interface PipelineTask {
  id: string;
  title: string;
  description: string;
  service: string;
  files: string[];
  type: "modify" | "create" | "delete" | "test";
  effort: "small" | "medium" | "large";
  effort_hours: number;
  dependencies: string[];
  risk_level: "HIGH" | "MEDIUM" | "LOW";
  acceptance_criteria: string[];
}

export interface TaskGroup {
  name: string;
  service: string;
  task_ids: string[];
  can_parallelize: boolean;
}

export interface AgentMessage {
  agent: string;
  message: string;
  timestamp: number;
}

export interface PipelineState {
  id: string;
  stage: PipelineStage;
  created_at?: number;
  updated_at?: number;
  requirements?: PipelineRequirements;
  conversation_history?: ChatMessage[];
  current_question?: string | null;
  needs_input?: boolean;
  
  // New backend fields
  report?: string | null;
  report_json?: Record<string, unknown> | null;
  verification?: {
    complete?: boolean;
    confidence?: string;
    gaps?: Array<Record<string, unknown>>;
    verified_paths?: number;
    recommendation?: string;
  } | null;
  iteration?: number;
  max_iterations?: number;
  gaps_history?: Array<Record<string, unknown>>;
  activity_log?: Array<{
    time: number;
    message: string;
    level: string;
  }>;
  error?: string | null;
  
  // Legacy fields (for backwards compatibility)
  direct_impacts?: ScoredImpact[];
  runtime_impacts?: ScoredImpact[];
  chain_impacts?: ScoredImpact[];
  scored_impacts?: ScoredImpact[];
  blast_radius?: BlastRadius;
  overall_risk?: "HIGH" | "MEDIUM" | "LOW" | "UNKNOWN";
  risk_summary?: string;
  recommendations?: string[];
  tasks?: PipelineTask[];
  task_groups?: TaskGroup[];
  execution_order?: string[][];
  total_effort_hours?: number;
  agent_messages?: AgentMessage[];
  current_agent?: string | null;
}


// ─── CODE GENERATION TYPES ───────────────────────────────────────────────────
// Types for the multi-agent code generation system

export type CodeGenStage =
  | "pending"
  | "designing"
  | "distributing"
  | "coordinating"
  | "implementing"
  | "verifying"
  | "fixing"
  | "awaiting_approval"
  | "approved"
  | "rejected"
  | "failed"
  | "design_complete";

/** A contract defining a shared interface between tasks */
export interface CodeGenContract {
  name: string;
  type: "function" | "class" | "interface" | "type" | "constant";
  defined_in: string;
  is_new: boolean;
  signature: string;
  implementation?: string;
  usage_example?: string;
  used_by: string[];
}

/** A change within a task */
export interface CodeGenChange {
  location: {
    type: "function" | "class" | "method" | "line_range" | "file_start" | "file_end";
    target: string;
    line_start?: number;
    line_end?: number;
  };
  change_type: "add" | "modify" | "delete" | "replace";
  description: string;
  before?: string;
  after?: string;
}

/** A single task for an implementation agent */
export interface CodeGenTask {
  id: string;
  phase: number;
  file: string;
  service: string;
  language: string;
  action: "create" | "modify" | "delete";
  description: string;
  changes: CodeGenChange[];
  depends_on: string[];
  uses_contracts: string[];
  defines_contracts: string[];
}

/** Execution phase grouping tasks */
export interface ExecutionPhase {
  phase: number;
  description: string;
  tasks: string[];
  parallel: boolean;
  wait_for_completion: boolean;
}

/** The complete plan.json structure */
export interface CodeGenPlan {
  version: string;
  change_request: string;
  analysis?: {
    summary: string;
    reasoning: string;
    existing_patterns: Array<{
      pattern: string;
      location: string;
      reuse: boolean;
      rationale: string;
    }>;
    risks: string[];
    assumptions: string[];
  };
  design?: {
    decisions: Array<{
      decision: string;
      rationale: string;
      alternatives_considered?: string[];
    }>;
    conventions: Record<string, string>;
  };
  contracts: Record<string, CodeGenContract>;
  execution: ExecutionPhase[];
  tasks: Record<string, CodeGenTask>;
}

/** Output from an implementation agent */
export interface AgentOutput {
  task_id: string;
  file: string;
  diff: string;
  status: "success" | "error" | "pending";
  error_message?: string;
  metadata?: Record<string, unknown>;
}

/** Verification issue */
export interface VerificationIssue {
  file: string;
  severity: "error" | "warning" | "info";
  issue: string;
  line?: number;
  suggestion?: string;
}

/** Verification result */
export interface CodeGenVerification {
  passed: boolean;
  tool_results: {
    lint?: { passed: boolean; errors: VerificationIssue[] };
    tests?: { passed: boolean; failures: string[] };
  };
  llm_results?: {
    passed: boolean;
    issues: VerificationIssue[];
    summary: string;
  };
  issues: VerificationIssue[];
}

/** Full code generation state */
export interface CodeGenState {
  id: string;
  stage: CodeGenStage;
  created_at: number;
  updated_at: number;
  
  // Input
  impact_report?: {
    pipeline_id: string;
    change_request: string;
    report: string;
    report_json: Record<string, unknown>;
    requirements: string;
  };
  
  // Plan
  plan?: CodeGenPlan;
  
  // Implementation results
  diffs: AgentOutput[];
  
  // Verification
  verification?: CodeGenVerification;
  
  // Retry tracking
  iteration: number;
  max_iterations: number;
  failed_tasks: string[];
  
  // Activity log
  activity_log: Array<{
    time: number;
    message: string;
    level: string;
  }>;
  
  // Error
  error?: string;
}

/** Result of approved code generation */
export interface CodeGenResult {
  success: boolean;
  plan?: CodeGenPlan;
  diffs: AgentOutput[];
  verification?: CodeGenVerification;
  error?: string;
}


// ─── Reverse Engineer Pipeline (Pipeline 3) ──────────────────────────────────

/** Pipeline stage for the RE pipeline */
export type REStage =
  | "uploading"
  | "parsing"
  | "extracting"
  | "inferring"
  | "gap_review"
  | "writing"
  | "complete"
  | "failed";

/** Confidence level for a spec claim */
export type REConfidence = "CONFIRMED" | "INFERRED" | "GAP";

/** A single generated spec section */
export interface SpecSection {
  section_id: string;
  title: string;
  content_md: string;
  confidence_score: number; // 0.0 – 1.0
  gap_count: number;
  generated_at: number;
}

/** Activity log entry from the pipeline */
export interface REActivity {
  time: number;
  message: string;
  level: "info" | "warning" | "error";
  event_type: string;
  metadata: Record<string, unknown>;
}

/** Full state of one Reverse Engineer pipeline session */
export interface ReverseEngineerSession {
  id: string;
  stage: REStage;
  created_at: number;
  updated_at: number;
  log_file_name: string;
  user_comments?: string;

  // Stage outputs (progressively populated)
  extracted_facts?: {
    service_count: number;
    endpoint_count: number;
    trace_count: number;
    services: Array<{ name: string; event_count: number }>;
    endpoints: Array<{ method: string; path_template: string }>;
    trace_flows: Array<{ trace_id: string; scenario_name: string; outcome: string }>;
    kafka_topics: Array<{ topic: string; producers: string[]; consumers: string[] }>;
    resilience_patterns: Array<{ pattern_name: string; service: string }>;
    slo_metrics: Array<{ metric_name: string; service: string; status: string }>;
  };
  asg?: {
    confirmed_count: number;
    inferred_count: number;
    gap_count: number;
  };
  spec_sections: Record<string, SpecSection>;

  // Progress
  current_stage_detail: string;
  activity_log: REActivity[];
  error?: string;

  // Convenience
  service_count: number;
  spec_section_count: number;
  available_sections: string[];
}

/** All available spec section IDs */
export const RE_SECTION_IDS = [
  "executive_summary",
  "service_inventory",
  "api_catalog",
  "business_logic",
  "event_topology",
  "data_model",
  "cross_cutting",
  "slos_and_observability",
  "resilience_patterns",
  "tech_stack",
  "risks_and_gaps",
  "confidence_report",
] as const;

export type RESectionId = typeof RE_SECTION_IDS[number];
