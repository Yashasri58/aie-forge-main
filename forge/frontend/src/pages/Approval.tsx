import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import {
  CheckCircle2,
  Edit3,
  Box,
  GitBranch,
  FileCode,
  Tag,
  Gauge,
  ArrowRight,
} from "lucide-react";
import { Page, Header, Card, Button, Badge, Progress } from "../components/ui";
import { getPipelineStatus, confirmRequirements } from "../api";
import type { PipelineState } from "../types";

export default function Approval() {
  const { pipelineId } = useParams();
  const navigate = useNavigate();
  
  const [pipeline, setPipeline] = useState<PipelineState | null>(null);
  const [loading, setLoading] = useState(true);
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    if (pipelineId) {
      loadPipeline(pipelineId);
    }
  }, [pipelineId]);

  // Redirect if not in the right stage
  useEffect(() => {
    if (pipeline && pipeline.stage !== "requirements_ready") {
      if (pipeline.stage === "gathering") {
        navigate(`/chat/${pipeline.id}`);
      } else if (["analyzing", "verifying", "filling_gaps"].includes(pipeline.stage)) {
        navigate(`/pipeline/${pipeline.id}`);
      } else if (pipeline.stage === "awaiting_approval") {
        navigate(`/results/${pipeline.id}`);
      }
    }
  }, [pipeline, navigate]);

  async function loadPipeline(id: string) {
    try {
      const state = await getPipelineStatus(id);
      setPipeline(state);
    } catch (err) {
      console.error("Failed to load pipeline:", err);
      navigate("/");
    } finally {
      setLoading(false);
    }
  }

  async function handleConfirm() {
    if (!pipelineId) return;
    
    setConfirming(true);
    
    // Navigate to Pipeline page IMMEDIATELY - don't wait for API
    // The Pipeline page will poll for status and show progress
    navigate(`/pipeline/${pipelineId}`);
    
    // Fire the confirm API in the background (non-blocking)
    confirmRequirements(pipelineId).catch((err) => {
      console.error("Confirm failed:", err);
    });
  }

  function handleEdit() {
    if (pipelineId) {
      navigate(`/chat/${pipelineId}`);
    }
  }

  if (loading || !pipeline) {
    return (
      <Page className="flex items-center justify-center">
        <div className="shimmer w-64 h-32 rounded-xl" />
      </Page>
    );
  }

  const req = pipeline.requirements;
  const clarityScore = req?.clarity_score || 0;

  return (
    <Page>
      <Header
        backTo={`/chat/${pipelineId}`}
        backLabel="Back to Chat"
        step={{ current: 2, total: 4, label: "Review" }}
      />

      <div className="flex-1 flex flex-col items-center justify-center max-w-3xl mx-auto w-full py-8">
        {/* Success Icon */}
        <motion.div
          className="w-20 h-20 rounded-full bg-[var(--color-success-subtle)] flex items-center justify-center mb-6"
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ type: "spring", duration: 0.5 }}
        >
          <CheckCircle2 size={40} className="text-[var(--color-success)]" />
        </motion.div>

        <motion.h1
          className="text-2xl font-semibold text-[var(--color-text-primary)] mb-2"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
        >
          Requirements Collected
        </motion.h1>

        <motion.p
          className="text-[var(--color-text-secondary)] mb-8"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
        >
          Review the details below before starting impact analysis
        </motion.p>

        {/* Requirements Card */}
        <motion.div
          className="w-full"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
        >
          <Card className="space-y-6">
            {/* Description */}
            {req?.description && (
              <div>
                <h3 className="text-sm font-medium text-[var(--color-text-muted)] uppercase tracking-wide mb-2">
                  Change Description
                </h3>
                <p className="text-[var(--color-text-primary)] leading-relaxed">
                  {req.description}
                </p>
              </div>
            )}

            <div className="divider" />

            {/* Scope Grid */}
            <div className="grid grid-cols-3 gap-4">
              {/* Services */}
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <Box size={16} className="text-[var(--color-node-service)]" />
                  <span className="text-sm font-medium text-[var(--color-text-muted)]">
                    Services
                  </span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {(req?.services || []).length > 0 ? (
                    req?.services?.map((s) => (
                      <Badge key={s} variant="accent">
                        {s}
                      </Badge>
                    ))
                  ) : (
                    <span className="text-sm text-[var(--color-text-dim)]">
                      None specified
                    </span>
                  )}
                </div>
              </div>

              {/* Functions */}
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <GitBranch size={16} className="text-[var(--color-node-function)]" />
                  <span className="text-sm font-medium text-[var(--color-text-muted)]">
                    Functions
                  </span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {(req?.functions || []).length > 0 ? (
                    req?.functions?.map((f) => (
                      <Badge key={f}>
                        <code className="text-xs">{f}</code>
                      </Badge>
                    ))
                  ) : (
                    <span className="text-sm text-[var(--color-text-dim)]">
                      None specified
                    </span>
                  )}
                </div>
              </div>

              {/* Files */}
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <FileCode size={16} className="text-[var(--color-node-file)]" />
                  <span className="text-sm font-medium text-[var(--color-text-muted)]">
                    Files
                  </span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {(req?.files || []).length > 0 ? (
                    req?.files?.map((f) => (
                      <Badge key={f}>
                        <code className="text-xs">{f}</code>
                      </Badge>
                    ))
                  ) : (
                    <span className="text-sm text-[var(--color-text-dim)]">
                      None specified
                    </span>
                  )}
                </div>
              </div>
            </div>

            <div className="divider" />

            {/* Change Type & Clarity */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-2">
                  <Tag size={16} className="text-[var(--color-text-muted)]" />
                  <span className="text-sm text-[var(--color-text-muted)]">
                    Change Type:
                  </span>
                  <Badge variant={req?.change_type === "feature" ? "accent" : "default"}>
                    {req?.change_type || "Unknown"}
                  </Badge>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2">
                  <Gauge size={16} className="text-[var(--color-text-muted)]" />
                  <span className="text-sm text-[var(--color-text-muted)]">
                    Clarity Score
                  </span>
                </div>
                <div className="flex items-center gap-2 w-32">
                  <Progress value={clarityScore} max={10} />
                  <span className="text-sm font-mono text-[var(--color-text-primary)]">
                    {clarityScore}/10
                  </span>
                </div>
              </div>
            </div>
          </Card>
        </motion.div>

        {/* Action Buttons */}
        <motion.div
          className="flex gap-4 mt-8"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
        >
          <Button
            variant="secondary"
            onClick={handleEdit}
            icon={<Edit3 size={16} />}
          >
            Edit Requirements
          </Button>
          <Button
            variant="primary"
            size="lg"
            onClick={handleConfirm}
            loading={confirming}
            icon={!confirming && <CheckCircle2 size={18} />}
          >
            Confirm & Start Analysis
            <ArrowRight size={16} />
          </Button>
        </motion.div>
      </div>
    </Page>
  );
}
