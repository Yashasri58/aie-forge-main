import { useEffect, useState, useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Loader2,
  Code2,
  FileCode,
  Layers,
  RefreshCw,
  Eye,
} from "lucide-react";
import { Page, Header, Card, Button, Progress } from "../components/ui";
import { DiffList } from "../components/DiffViewer";
import PlanViewer from "../components/PlanViewer";
import {
  startCodeGen,
  getCodeGenStatus,
  getCodeGenPlan,
  getCodeGenDiffs,
} from "../api";
import type { CodeGenState, CodeGenPlan, AgentOutput, CodeGenStage } from "../types";

type ViewMode = "plan" | "diffs";

const STAGE_ORDER: CodeGenStage[] = [
  "pending",
  "designing",
  "coordinating",
  "implementing",
  "verifying",
  "awaiting_approval",
];

const STAGE_LABELS: Record<CodeGenStage, string> = {
  pending: "Pending",
  designing: "Designing Plan",
  coordinating: "Coordinating Tasks",
  implementing: "Generating Code",
  verifying: "Verifying Changes",
  awaiting_approval: "Awaiting Approval",
  approved: "Approved",
  rejected: "Rejected",
  failed: "Failed",
};

export default function CodeGen() {
  const { pipelineId } = useParams();
  const navigate = useNavigate();

  const [state, setState] = useState<CodeGenState | null>(null);
  const [plan, setPlan] = useState<CodeGenPlan | null>(null);
  const [diffs, setDiffs] = useState<AgentOutput[]>([]);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>("plan");
  const [error, setError] = useState<string | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll log
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [state?.activity_log?.length]);

  // Start code generation or load existing state
  useEffect(() => {
    if (pipelineId) {
      initCodeGen(pipelineId);
    }
  }, [pipelineId]);

  // SSE stream for live progress while in progress
  useEffect(() => {
    if (!state?.id) return;

    const isFullyTerminal = ["approved", "rejected", "failed", "awaiting_approval"].includes(state.stage);
    if (isFullyTerminal) return;

    const codegenId = state.id;
    const es = new EventSource(`/codegen/${codegenId}/stream`);

    es.onmessage = () => { refreshState(codegenId); };
    es.addEventListener("stage", () => { refreshState(codegenId); });
    es.addEventListener("done", () => { es.close(); refreshState(codegenId); });
    es.onerror = () => {
      es.close();
      setTimeout(() => { refreshState(codegenId); }, 500);
    };

    return () => { es.close(); };
  }, [state?.id, state?.stage]);

  // Polling fallback — 3s interval while pipeline is running.
  // SSE cascade alone is unreliable (404 fires once per mount, not per stage).
  // This guarantees the UI always reflects backend state.
  useEffect(() => {
    if (!state?.id) return;
    const isTerminal = ["approved", "rejected", "failed", "awaiting_approval"].includes(state.stage);
    if (isTerminal) return;

    const codegenId = state.id;
    const timer = setInterval(() => { refreshState(codegenId); }, 3000);
    return () => clearInterval(timer);
  }, [state?.id, state?.stage]);  async function initCodeGen(pipelineId: string) {
    setLoading(true);
    setError(null);

    try {
      // First, try to load existing codegen state (handles direct navigation to /gen/:codegenId)
      let codegenState: CodeGenState | null = null;
      try {
        codegenState = await getCodeGenStatus(pipelineId);
      } catch {
        // Not a codegen ID — treat as pipeline ID and start new codegen
      }

      if (!codegenState) {
        // Try to start code generation from a pipeline ID
        setStarting(true);
        codegenState = await startCodeGen(pipelineId);
      }

      setState(codegenState);

      // Load plan if available
      const [newPlan, newDiffs] = await Promise.all([
        getCodeGenPlan(codegenState.id).catch(() => null),
        getCodeGenDiffs(codegenState.id).catch(() => []),
      ]);
      if (newPlan) setPlan(newPlan);
      if (newDiffs.length > 0) setDiffs(newDiffs);

    } catch (err: any) {
      setError(err.message || "Failed to load code generation");
    } finally {
      setLoading(false);
      setStarting(false);
    }
  }

  async function refreshState(codegenId: string) {
    try {
      const [newState, newPlan, newDiffs] = await Promise.all([
        getCodeGenStatus(codegenId),
        getCodeGenPlan(codegenId).catch(() => null),
        getCodeGenDiffs(codegenId).catch(() => []),
      ]);

      setState(newState);
      if (newPlan) setPlan(newPlan);
      if (newDiffs.length > 0) setDiffs(newDiffs);

      // Auto-switch to diffs view when implementation starts
      if (newState.stage === "implementing" && newDiffs.length > 0) {
        setViewMode("diffs");
      }
    } catch (err: any) {
      console.error("Failed to refresh state:", err);
    }
  }

  function getStageProgress(): number {
    if (!state) return 0;
    const idx = STAGE_ORDER.indexOf(state.stage);
    if (idx === -1) return 100; // Terminal state
    return Math.round(((idx + 1) / STAGE_ORDER.length) * 100);
  }

  function getStageStatus(stage: CodeGenStage): "complete" | "active" | "pending" | "error" {
    if (!state) return "pending";
    if (state.stage === "failed") return stage === state.stage ? "error" : "pending";

    const currentIdx = STAGE_ORDER.indexOf(state.stage);
    const stageIdx = STAGE_ORDER.indexOf(stage);

    if (stageIdx < currentIdx) return "complete";
    if (stageIdx === currentIdx) return "active";
    return "pending";
  }

  // While the initial POST /codegen/start is in-flight, show a full-screen
  // "starting" view with the stage bar skeleton and a live SSE log feed.
  if (loading) {
    return (
      <Page>
        <Header backTo="/" backLabel="Dashboard" step={{ current: 5, total: 5, label: "Code Generation" }} />

        <div className="flex-1 flex gap-6 min-h-0">
          {/* Left: pipeline skeleton */}
          <div className="flex-1 flex flex-col min-h-0">
            {/* Progress bar */}
            <Card className="mb-4">
              <div className="flex items-center gap-2 mb-3">
                <Loader2 size={18} className="animate-spin text-[var(--color-accent)]" />
                <span className="font-medium text-[var(--color-text-primary)]">
                  {starting ? "Starting Code Generation" : "Loading…"}
                </span>
              </div>
              <Progress value={0} />
            </Card>

            {/* Stage steps skeleton */}
            <div className="flex items-center gap-2 mb-4 overflow-x-auto pb-2">
              {STAGE_ORDER.slice(1).map((stage, i) => (
                <div key={stage} className="flex items-center gap-2">
                  {i > 0 && <div className="w-8 h-0.5 bg-[var(--color-glass-border)]" />}
                  <div className="flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)]">
                    {STAGE_LABELS[stage]}
                  </div>
                </div>
              ))}
            </div>

            {/* Empty content area */}
            <Card className="flex-1 flex items-center justify-center">
              <div className="text-center space-y-3">
                <Loader2 size={32} className="animate-spin text-[var(--color-accent)] mx-auto" />
                <p className="text-[var(--color-text-muted)] text-sm">Initialising pipeline…</p>
              </div>
            </Card>
          </div>

          {/* Right: live log panel */}
          <div className="w-80 flex flex-col gap-4">
            <Card className="flex flex-col overflow-hidden flex-1">
              <div className="flex items-center justify-between px-1 pb-2 border-b border-[var(--color-glass-border)]">
                <h3 className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wider">Activity</h3>
                <div className="flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-success)] animate-pulse" />
                  <span className="text-xs text-[var(--color-text-muted)]">Live</span>
                </div>
              </div>
              <div className="space-y-1 overflow-y-auto pt-2 font-mono text-xs flex-1" ref={logEndRef as React.RefObject<HTMLDivElement>}>
                <div className="flex gap-2">
                  <span className="text-[var(--color-text-muted)] shrink-0 opacity-50">
                    {new Date().toLocaleTimeString("en", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                  </span>
                  <span className="text-[var(--color-text-muted)]">
                    {starting ? "Starting code generation pipeline…" : "Loading session…"}
                  </span>
                </div>
              </div>
            </Card>

            <Button variant="ghost" className="w-full" onClick={() => navigate("/")}>
              Back to Dashboard
            </Button>
          </div>
        </div>
      </Page>
    );
  }

  if (error) {
    return (
      <Page>
        <Header backTo="/" backLabel="Dashboard" />
        <Card className="max-w-md mx-auto mt-12 text-center">
          <XCircle size={48} className="mx-auto mb-4 text-[var(--color-error)]" />
          <h2 className="text-lg font-medium text-[var(--color-text-primary)] mb-2">
            Code Generation Failed
          </h2>
          <p className="text-sm text-[var(--color-text-secondary)] mb-4">{error}</p>
          <Button variant="primary" onClick={() => navigate("/")}>
            Return to Dashboard
          </Button>
        </Card>
      </Page>
    );
  }

  if (!state) return null;

  const isTerminal = ["approved", "rejected", "failed"].includes(state.stage);
  const canReview = state.stage === "awaiting_approval";
  const isInProgress = !isTerminal && !canReview; // still running

  return (
    <Page>
      <Header
        backTo="/"
        backLabel="Dashboard"
        step={{ current: 5, total: 5, label: "Code Generation" }}
      />

      <div className="flex-1 flex gap-6 min-h-0">
        {/* Left: Main Content */}
        <div className="flex-1 flex flex-col min-h-0">
          {/* Progress Bar */}
          <Card className="mb-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Code2 size={18} className="text-[var(--color-accent)]" />
                <span className="font-medium text-[var(--color-text-primary)]">
                  {STAGE_LABELS[state.stage]}
                </span>
              </div>
              {!isTerminal && (
                <span className="text-sm text-[var(--color-text-muted)]">
                  Iteration {state.iteration}/{state.max_iterations || 3}
                </span>
              )}
            </div>
            <Progress value={getStageProgress()} />
          </Card>

          {/* Stage Steps */}
          <div className="flex items-center gap-2 mb-4 overflow-x-auto pb-2">
            {STAGE_ORDER.slice(1).map((stage, i) => {
              const status = getStageStatus(stage);
              return (
                <div key={stage} className="flex items-center gap-2">
                  {i > 0 && (
                    <div
                      className={`w-8 h-0.5 ${
                        status === "complete"
                          ? "bg-[var(--color-success)]"
                          : "bg-[var(--color-glass-border)]"
                      }`}
                    />
                  )}
                  <div
                    className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap ${
                      status === "active"
                        ? "bg-[var(--color-accent)] text-white"
                        : status === "complete"
                        ? "bg-[var(--color-success-subtle)] text-[var(--color-success)]"
                        : status === "error"
                        ? "bg-[var(--color-error-subtle)] text-[var(--color-error)]"
                        : "bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)]"
                    }`}
                  >
                    {status === "complete" && <CheckCircle2 size={12} />}
                    {status === "active" && <Loader2 size={12} className="animate-spin" />}
                    {status === "error" && <XCircle size={12} />}
                    {STAGE_LABELS[stage]}
                  </div>
                </div>
              );
            })}
          </div>

          {/* View Toggle */}
          <div className="flex gap-2 mb-4">
            <button
              onClick={() => setViewMode("plan")}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                viewMode === "plan"
                  ? "bg-[var(--color-accent)] text-white"
                  : "bg-[var(--color-bg-elevated)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)]"
              }`}
            >
              <Layers size={16} />
              Plan
            </button>
            <button
              onClick={() => setViewMode("diffs")}
              disabled={diffs.length === 0}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                viewMode === "diffs"
                  ? "bg-[var(--color-accent)] text-white"
                  : "bg-[var(--color-bg-elevated)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)]"
              } disabled:opacity-50 disabled:cursor-not-allowed`}
            >
              <FileCode size={16} />
              Diffs ({diffs.length})
            </button>
          </div>

          {/* Content Area */}
          <div className="flex-1 overflow-y-auto">
            {viewMode === "plan" && plan ? (
              <PlanViewer plan={plan} />
            ) : viewMode === "plan" && !plan ? (
              <Card className="h-full flex items-center justify-center">
                <div className="text-center space-y-3">
                  <Loader2 size={32} className="animate-spin text-[var(--color-accent)] mx-auto" />
                  <p className="text-[var(--color-text-muted)]">Generating plan...</p>
                </div>
              </Card>
            ) : viewMode === "diffs" && diffs.length > 0 ? (
              <DiffList
                diffs={diffs.map((d) => ({
                  file: d.file,
                  diff: d.diff,
                  status: d.status === "success" ? "success" : d.status === "error" ? "error" : "pending",
                }))}
              />
            ) : (
              <Card className="h-full flex items-center justify-center">
                <p className="text-[var(--color-text-muted)]">No diffs generated yet</p>
              </Card>
            )}
          </div>
        </div>

        {/* Right: Actions Panel */}
        <div className="w-80 flex flex-col gap-4">
          {/* Status Card */}
          <Card>
            <div className="flex items-center gap-2 mb-3">
              {state.stage === "awaiting_approval" ? (
                <CheckCircle2 size={18} className="text-[var(--color-success)]" />
              ) : state.stage === "failed" ? (
                <XCircle size={18} className="text-[var(--color-error)]" />
              ) : (
                <Loader2 size={18} className="animate-spin text-[var(--color-accent)]" />
              )}
              <span className="font-medium text-[var(--color-text-primary)]">
                {isTerminal ? "Generation Complete" : "In Progress"}
              </span>
            </div>
            <p className="text-sm text-[var(--color-text-secondary)]">
              {state.stage === "awaiting_approval"
                ? "Code changes are ready for review. Approve to apply them to your codebase."
                : state.stage === "failed"
                ? "Code generation failed. Check the logs for details."
                : "Code generation is in progress. This may take a few minutes."}
            </p>
          </Card>

          {/* Stats */}
          <Card>
            <h3 className="font-medium text-[var(--color-text-primary)] mb-3">Statistics</h3>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-[var(--color-text-muted)]">Files Changed</span>
                <span className="text-[var(--color-text-primary)] font-medium">
                  {diffs.length}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-[var(--color-text-muted)]">Tasks</span>
                <span className="text-[var(--color-text-primary)] font-medium">
                  {plan?.tasks ? Object.keys(plan.tasks).length : 0}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-[var(--color-text-muted)]">Contracts</span>
                <span className="text-[var(--color-text-primary)] font-medium">
                  {plan?.contracts ? Object.keys(plan.contracts).length : 0}
                </span>
              </div>
              {state.verification && (
                <div className="flex justify-between">
                  <span className="text-[var(--color-text-muted)]">Issues</span>
                  <span
                    className={`font-medium ${
                      state.verification.issues.length > 0
                        ? "text-[var(--color-warning)]"
                        : "text-[var(--color-success)]"
                    }`}
                  >
                    {state.verification.issues.length}
                  </span>
                </div>
              )}
            </div>
          </Card>

          {/* Verification Issues */}
          {state.verification && state.verification.issues.length > 0 && (
            <Card className="border-[var(--color-warning)] bg-[var(--color-warning-subtle)]">
              <div className="flex items-center gap-2 text-[var(--color-warning)] mb-2">
                <AlertTriangle size={16} />
                <span className="font-medium">Verification Issues</span>
              </div>
              <ul className="space-y-1 text-sm text-[var(--color-text-secondary)]">
                {state.verification.issues.slice(0, 3).map((issue, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <span className="text-[var(--color-warning)]">•</span>
                    <span>{issue.issue}</span>
                  </li>
                ))}
                {state.verification.issues.length > 3 && (
                  <li className="text-[var(--color-text-muted)]">
                    +{state.verification.issues.length - 3} more
                  </li>
                )}
              </ul>
            </Card>
          )}

          {/* Live Activity Log */}
          {state.activity_log && state.activity_log.length > 0 && (
            <Card className="flex flex-col overflow-hidden">
              <div className="flex items-center justify-between px-1 pb-2 border-b border-[var(--color-glass-border)]">
                <h3 className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wider">Activity</h3>
                <div className="flex items-center gap-1.5">
                  {!isTerminal && (
                    <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-success)] animate-pulse" />
                  )}
                  <span className="text-xs text-[var(--color-text-muted)]">
                    {isTerminal ? "Done" : "Live"}
                  </span>
                </div>
              </div>
              <div className="space-y-1 max-h-48 overflow-y-auto pt-2 font-mono text-xs" ref={logEndRef as React.RefObject<HTMLDivElement>}>
                {state.activity_log.map((entry: { time: number; message: string; level: string }, i: number) => {
                  const ts = new Date(entry.time * 1000).toLocaleTimeString("en", {
                    hour: "2-digit", minute: "2-digit", second: "2-digit",
                  });
                  const color =
                    entry.level === "success" ? "text-[var(--color-success)]"
                    : entry.level === "error" ? "text-[var(--color-error)]"
                    : entry.level === "warning" ? "text-[var(--color-warning)]"
                    : "text-[var(--color-text-muted)]";
                  return (
                    <div key={i} className="flex gap-2">
                      <span className="text-[var(--color-text-muted)] shrink-0 opacity-50">{ts}</span>
                      <span className={color}>{entry.message}</span>
                    </div>
                  );
                })}
              </div>
            </Card>
          )}

          {/* Action Buttons */}
          <div className="space-y-3 mt-auto">

            {/* Loading indicator — visible only while pipeline is running */}
            {isInProgress && (
              <Card className="border-[var(--color-accent)] bg-[var(--color-accent-subtle)]">
                <div className="flex items-center gap-3">
                  <Loader2 size={20} className="animate-spin text-[var(--color-accent)] shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-[var(--color-accent)]">
                      {STAGE_LABELS[state.stage] ?? "Generating…"}
                    </p>
                    <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
                      Iteration {state.iteration}/{state.max_iterations || 3} · Please wait
                    </p>
                  </div>
                </div>
                <div className="mt-3 h-1 w-full rounded-full bg-[var(--color-glass-border)] overflow-hidden">
                  <div
                    className="h-full rounded-full bg-[var(--color-accent)]"
                    style={{ width: `${getStageProgress()}%`, transition: "width 0.6s ease" }}
                  />
                </div>
              </Card>
            )}

            {/* Review & Approve — only at awaiting_approval */}
            {canReview && (
              <Button
                variant="success"
                size="lg"
                className="w-full"
                onClick={() => navigate(`/gen/${state.id}/approve`)}
                icon={<Eye size={18} />}
              >
                Review & Approve
              </Button>
            )}

            {/* Refresh — only when flow is complete (awaiting_approval or terminal) */}
            {(canReview || isTerminal) && (
              <Button
                variant="ghost"
                className="w-full"
                onClick={() => state?.id && refreshState(state.id)}
                icon={<RefreshCw size={16} />}
              >
                Refresh Status
              </Button>
            )}

            {/* Back to Dashboard — only when not mid-run */}
            {(canReview || isTerminal) && (
              <Button
                variant="ghost"
                className="w-full"
                onClick={() => navigate("/")}
              >
                Back to Dashboard
              </Button>
            )}
          </div>
        </div>
      </div>
    </Page>
  );
}
