import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  MessageSquare,
  ChevronLeft,
  ChevronRight,
  FileCode,
  Plus,
  Minus,
  Send,
  Loader2,
} from "lucide-react";
import { Page, Header, Card, Button, Badge } from "../components/ui";
import { DiffViewer } from "../components/DiffViewer";
import {
  getCodeGenStatus,
  getCodeGenDiffs,
  approveCodeGen,
  refineCodeGen,
} from "../api";
import type { CodeGenState, AgentOutput } from "../types";

export default function DiffApproval() {
  const { codegenId } = useParams();
  const navigate = useNavigate();

  const [state, setState] = useState<CodeGenState | null>(null);
  const [diffs, setDiffs] = useState<AgentOutput[]>([]);
  const [loading, setLoading] = useState(true);
  const [approving, setApproving] = useState(false);
  const [refining, setRefining] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [showFeedback, setShowFeedback] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (codegenId) {
      loadData(codegenId);
    }
  }, [codegenId]);

  async function loadData(id: string) {
    setLoading(true);
    setError(null);

    try {
      const [codegenState, codegenDiffs] = await Promise.all([
        getCodeGenStatus(id),
        getCodeGenDiffs(id),
      ]);

      setState(codegenState);
      setDiffs(codegenDiffs);

      // Redirect if not in awaiting_approval state
      if (codegenState.stage !== "awaiting_approval") {
        navigate(`/codegen/${codegenState.impact_report?.pipeline_id || codegenId}`);
      }
    } catch (err: any) {
      setError(err.message || "Failed to load code generation data");
    } finally {
      setLoading(false);
    }
  }

  async function handleApprove() {
    if (!codegenId) return;

    setApproving(true);
    try {
      await approveCodeGen(codegenId, true);
      navigate("/");
    } catch (err: any) {
      setError(err.message || "Failed to approve");
    } finally {
      setApproving(false);
    }
  }

  async function handleReject() {
    if (!codegenId) return;

    setApproving(true);
    try {
      await approveCodeGen(codegenId, false, "User rejected changes");
      navigate("/");
    } catch (err: any) {
      setError(err.message || "Failed to reject");
    } finally {
      setApproving(false);
    }
  }

  async function handleRefine() {
    if (!codegenId || !feedback.trim()) return;

    setRefining(true);
    try {
      await refineCodeGen(codegenId, feedback);
      setShowFeedback(false);
      setFeedback("");
      // Redirect back to codegen page to see progress
      navigate(`/codegen/${state?.impact_report?.pipeline_id || codegenId}`);
    } catch (err: any) {
      setError(err.message || "Failed to submit feedback");
    } finally {
      setRefining(false);
    }
  }

  function nextDiff() {
    if (selectedIndex < diffs.length - 1) {
      setSelectedIndex(selectedIndex + 1);
    }
  }

  function prevDiff() {
    if (selectedIndex > 0) {
      setSelectedIndex(selectedIndex - 1);
    }
  }

  function getDiffStats(): { additions: number; deletions: number; files: number } {
    let additions = 0;
    let deletions = 0;

    for (const diff of diffs) {
      for (const line of diff.diff.split("\n")) {
        if (line.startsWith("+") && !line.startsWith("+++")) additions++;
        if (line.startsWith("-") && !line.startsWith("---")) deletions++;
      }
    }

    return { additions, deletions, files: diffs.length };
  }

  if (loading) {
    return (
      <Page className="flex items-center justify-center">
        <div className="text-center space-y-4">
          <Loader2 size={48} className="animate-spin text-[var(--color-accent)] mx-auto" />
          <p className="text-[var(--color-text-muted)]">Loading changes...</p>
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
            Error
          </h2>
          <p className="text-sm text-[var(--color-text-secondary)] mb-4">{error}</p>
          <Button variant="primary" onClick={() => navigate("/")}>
            Return to Dashboard
          </Button>
        </Card>
      </Page>
    );
  }

  if (!state || diffs.length === 0) {
    return (
      <Page>
        <Header backTo="/" backLabel="Dashboard" />
        <Card className="max-w-md mx-auto mt-12 text-center">
          <FileCode size={48} className="mx-auto mb-4 text-[var(--color-text-muted)]" />
          <h2 className="text-lg font-medium text-[var(--color-text-primary)] mb-2">
            No Changes
          </h2>
          <p className="text-sm text-[var(--color-text-secondary)] mb-4">
            No code changes were generated.
          </p>
          <Button variant="primary" onClick={() => navigate("/")}>
            Return to Dashboard
          </Button>
        </Card>
      </Page>
    );
  }

  const currentDiff = diffs[selectedIndex];
  const stats = getDiffStats();

  return (
    <Page>
      <Header
        backTo={`/codegen/${state.impact_report?.pipeline_id || codegenId}`}
        backLabel="Code Generation"
        step={{ current: 5, total: 5, label: "Review Changes" }}
      />

      <div className="flex-1 flex gap-6 min-h-0">
        {/* Left: Diff Viewer */}
        <div className="flex-1 flex flex-col min-h-0">
          {/* Navigation */}
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={prevDiff}
                disabled={selectedIndex === 0}
                icon={<ChevronLeft size={16} />}
              >
                Prev
              </Button>
              <span className="text-sm text-[var(--color-text-secondary)]">
                {selectedIndex + 1} / {diffs.length} files
              </span>
              <Button
                variant="ghost"
                size="sm"
                onClick={nextDiff}
                disabled={selectedIndex === diffs.length - 1}
                icon={<ChevronRight size={16} />}
              >
                Next
              </Button>
            </div>

            <div className="flex items-center gap-4 text-sm">
              <span className="flex items-center gap-1 text-[var(--color-success)]">
                <Plus size={14} />
                {stats.additions} additions
              </span>
              <span className="flex items-center gap-1 text-[var(--color-error)]">
                <Minus size={14} />
                {stats.deletions} deletions
              </span>
            </div>
          </div>

          {/* File Tabs */}
          <div className="flex gap-1 mb-4 overflow-x-auto pb-2">
            {diffs.map((diff, i) => (
              <button
                key={diff.file}
                onClick={() => setSelectedIndex(i)}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-mono whitespace-nowrap transition-colors ${
                  i === selectedIndex
                    ? "bg-[var(--color-accent)] text-white"
                    : "bg-[var(--color-bg-elevated)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)]"
                }`}
              >
                <FileCode size={12} />
                {diff.file.split("/").pop()}
                {diff.status === "error" && (
                  <AlertTriangle size={12} className="text-[var(--color-warning)]" />
                )}
              </button>
            ))}
          </div>

          {/* Current Diff */}
          <div className="flex-1 overflow-y-auto">
            <motion.div
              key={selectedIndex}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.2 }}
            >
              <DiffViewer
                file={currentDiff.file}
                diff={currentDiff.diff}
                status={
                  currentDiff.status === "success"
                    ? "success"
                    : currentDiff.status === "error"
                    ? "error"
                    : "pending"
                }
              />

              {/* Error message */}
              {currentDiff.error_message && (
                <Card className="mt-4 border-[var(--color-error)] bg-[var(--color-error-subtle)]">
                  <div className="flex items-center gap-2 text-[var(--color-error)] mb-2">
                    <XCircle size={16} />
                    <span className="font-medium">Error</span>
                  </div>
                  <p className="text-sm text-[var(--color-text-secondary)]">
                    {currentDiff.error_message}
                  </p>
                </Card>
              )}
            </motion.div>
          </div>
        </div>

        {/* Right: Actions Panel */}
        <div className="w-80 flex-shrink-0 flex flex-col gap-4 overflow-y-auto" style={{maxHeight:"100%"}}>
          {/* Summary */}
          <Card>
            <h3 className="font-medium text-[var(--color-text-primary)] mb-3">
              Change Summary
            </h3>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-[var(--color-text-muted)]">Files</span>
                <span className="text-[var(--color-text-primary)] font-medium">
                  {stats.files}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-[var(--color-text-muted)]">Additions</span>
                <span className="text-[var(--color-success)] font-medium">
                  +{stats.additions}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-[var(--color-text-muted)]">Deletions</span>
                <span className="text-[var(--color-error)] font-medium">
                  -{stats.deletions}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-[var(--color-text-muted)]">Iteration</span>
                <span className="text-[var(--color-text-primary)]">
                  {state.iteration}/{state.max_iterations || 3}
                </span>
              </div>
            </div>
          </Card>

          {/* Verification */}
          {state.verification && (
            <Card>
              <h3 className="font-medium text-[var(--color-text-primary)] mb-3">
                Verification
              </h3>
              <div className="space-y-2">
                <Badge
                  variant={state.verification.passed ? "success" : "warning"}
                  className="mb-2"
                >
                  {state.verification.passed ? "Passed" : "Has Issues"}
                </Badge>

                {state.verification.issues.length > 0 && (
                  <ul className="space-y-1 text-xs">
                    {state.verification.issues.map((issue, i) => (
                      <li key={i} className="flex items-start gap-2">
                        <AlertTriangle
                          size={12}
                          className={`mt-0.5 ${
                            issue.severity === "error"
                              ? "text-[var(--color-error)]"
                              : "text-[var(--color-warning)]"
                          }`}
                        />
                        <span className="text-[var(--color-text-secondary)]">
                          {issue.issue}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </Card>
          )}

          {/* Feedback Form */}
          {showFeedback && (
            <Card className="border-[var(--color-accent)]">
              <h3 className="font-medium text-[var(--color-text-primary)] mb-3">
                Request Changes
              </h3>
              <textarea
                value={feedback}
                onChange={(e) => setFeedback(e.target.value)}
                placeholder="Describe what needs to change..."
                className="w-full h-24 px-3 py-2 text-sm bg-[var(--color-bg-elevated)] border border-[var(--color-glass-border)] rounded-lg resize-none focus:outline-none focus:border-[var(--color-accent)]"
              />
              <div className="flex gap-2 mt-3">
                <Button
                  variant="primary"
                  size="sm"
                  className="flex-1"
                  onClick={handleRefine}
                  loading={refining}
                  disabled={!feedback.trim()}
                  icon={!refining && <Send size={14} />}
                >
                  Submit
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setShowFeedback(false);
                    setFeedback("");
                  }}
                >
                  Cancel
                </Button>
              </div>
            </Card>
          )}

          {/* Action Buttons */}
          <div className="space-y-3">
            <Button
              variant="success"
              size="lg"
              className="w-full"
              onClick={handleApprove}
              loading={approving}
              icon={!approving && <CheckCircle2 size={18} />}
            >
              Approve Changes
            </Button>

            {!showFeedback && (
              <Button
                variant="secondary"
                className="w-full"
                onClick={() => setShowFeedback(true)}
                icon={<MessageSquare size={16} />}
              >
                Request Changes
              </Button>
            )}

            <Button
              variant="danger"
              className="w-full"
              onClick={handleReject}
              disabled={approving}
              icon={<XCircle size={16} />}
            >
              Reject All
            </Button>
          </div>
        </div>
      </div>
    </Page>
  );
}
