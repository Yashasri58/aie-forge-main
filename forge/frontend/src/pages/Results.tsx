import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import {
  XCircle,
  AlertTriangle,
  FileText,
  Layers,
  GitBranch,
  Sparkles,
  RotateCcw,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { Page, Header, Card, Button, Badge } from "../components/ui";
import { getPipelineStatus, approvePipeline } from "../api";
import type { PipelineState } from "../types";

type ViewMode = "report" | "layers";

export default function Results() {
  const { pipelineId } = useParams();
  const navigate = useNavigate();
  
  const [pipeline, setPipeline] = useState<PipelineState | null>(null);
  const [loading, setLoading] = useState(true);
  const [approving, setApproving] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>("report");
  const [expandedLayers, setExpandedLayers] = useState<Set<number>>(new Set([0, 1]));

  useEffect(() => {
    if (pipelineId) {
      loadPipeline(pipelineId);
    }
  }, [pipelineId]);

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

  async function handleApprove() {
    if (!pipelineId) return;
    
    setApproving(true);
    try {
      await approvePipeline(pipelineId, true);
      navigate(`/gen/${pipelineId}`);
    } catch (err) {
      console.error("Failed to approve:", err);
      setApproving(false);
    }
  }

  async function handleReject() {
    if (!pipelineId) return;
    
    try {
      await approvePipeline(pipelineId, false, "User rejected");
      navigate("/");
    } catch (err) {
      console.error("Failed to reject:", err);
    }
  }

  function toggleLayer(layer: number) {
    setExpandedLayers((prev) => {
      const next = new Set(prev);
      if (next.has(layer)) {
        next.delete(layer);
      } else {
        next.add(layer);
      }
      return next;
    });
  }

  if (loading || !pipeline) {
    return (
      <Page className="flex items-center justify-center">
        <div className="shimmer w-96 h-64 rounded-xl" />
      </Page>
    );
  }

  const verification = pipeline.verification;
  const report = pipeline.report || "";

  return (
    <Page>
      <Header
        backTo="/"
        backLabel="Dashboard"
        step={{ current: 4, total: 4, label: "Results" }}
      />

      <div className="flex-1 flex gap-6 min-h-0">
        {/* Left: Main Content */}
        <div className="flex-1 flex flex-col min-h-0">
          {/* Stats Row */}
          <div className="grid grid-cols-4 gap-4 mb-4">
            <Card className="text-center py-3">
              <div className="text-2xl font-bold text-[var(--color-text-primary)]">
                {countLayers(report)}
              </div>
              <div className="text-xs text-[var(--color-text-muted)]">Layers</div>
            </Card>
            <Card className="text-center py-3">
              <div className="text-2xl font-bold text-[var(--color-accent)]">
                {countServices(report)}
              </div>
              <div className="text-xs text-[var(--color-text-muted)]">Services</div>
            </Card>
            <Card className="text-center py-3">
              <div className="text-2xl font-bold text-[var(--color-warning)]">
                {pipeline.iteration || 1}
              </div>
              <div className="text-xs text-[var(--color-text-muted)]">Iterations</div>
            </Card>
            <Card className="text-center py-3">
              <Badge
                variant={
                  verification?.confidence === "HIGH" ? "success" :
                  verification?.confidence === "MEDIUM" ? "warning" : "error"
                }
              >
                {verification?.confidence || "N/A"}
              </Badge>
              <div className="text-xs text-[var(--color-text-muted)] mt-1">Confidence</div>
            </Card>
          </div>

          {/* View Mode Toggle */}
          <div className="flex gap-2 mb-4">
            <button
              onClick={() => setViewMode("report")}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                viewMode === "report"
                  ? "bg-[var(--color-accent)] text-white"
                  : "bg-[var(--color-bg-elevated)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)]"
              }`}
            >
              <FileText size={16} />
              Full Report
            </button>
            <button
              onClick={() => setViewMode("layers")}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                viewMode === "layers"
                  ? "bg-[var(--color-accent)] text-white"
                  : "bg-[var(--color-bg-elevated)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)]"
              }`}
            >
              <Layers size={16} />
              By Layer
            </button>
          </div>

          {/* Content Area */}
          <div className="flex-1 overflow-hidden">
            {viewMode === "report" ? (
              <ReportView report={report} />
            ) : (
              <LayersView 
                report={report} 
                expandedLayers={expandedLayers}
                toggleLayer={toggleLayer}
              />
            )}
          </div>
        </div>

        {/* Right: Actions Panel */}
        <div className="w-80 flex-shrink-0 flex flex-col gap-4 overflow-y-auto" style={{maxHeight:"100%"}}>
          {/* Verification Summary */}
          <Card>
            <h3 className="font-medium text-[var(--color-text-primary)] mb-3 flex items-center gap-2">
              <GitBranch size={16} />
              Verification
            </h3>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-[var(--color-text-muted)]">Verified Paths</span>
                <span className="text-[var(--color-success)] font-medium">
                  {verification?.verified_paths || 0}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-[var(--color-text-muted)]">Unresolved Gaps</span>
                <span className={`font-medium ${
                  (verification?.gaps?.length || 0) > 0 
                    ? "text-[var(--color-warning)]" 
                    : "text-[var(--color-success)]"
                }`}>
                  {verification?.gaps?.length || 0}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-[var(--color-text-muted)]">Iterations</span>
                <span className="text-[var(--color-text-primary)]">
                  {pipeline.iteration}/{pipeline.max_iterations}
                </span>
              </div>
            </div>
            {verification?.recommendation && (
              <p className="text-xs text-[var(--color-text-muted)] mt-3 p-2 bg-[var(--color-bg-elevated)] rounded">
                {verification.recommendation}
              </p>
            )}
          </Card>

          {/* Status Card */}
          <Card>
            <div className="flex items-center gap-2 text-[var(--color-success)] mb-2">
              <Sparkles size={16} />
              <span className="font-medium">Analysis Complete</span>
            </div>
            <p className="text-sm text-[var(--color-text-secondary)]">
              Review the full impact report and approve or reject the analysis.
            </p>
          </Card>

          {verification?.gaps && verification.gaps.length > 0 && (
            <Card className="border-[var(--color-warning)] bg-[var(--color-warning-subtle)]">
              <div className="flex items-center gap-2 text-[var(--color-warning)] mb-2">
                <AlertTriangle size={16} />
                <span className="font-medium">Incomplete Coverage</span>
              </div>
              <p className="text-sm text-[var(--color-text-secondary)]">
                {verification.gaps.length} call path(s) could not be fully verified.
              </p>
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
              icon={!approving && <Sparkles size={18} />}
            >
              Approve & Generate Code
            </Button>
            <Button
              variant="danger"
              className="w-full"
              onClick={handleReject}
              icon={<XCircle size={16} />}
            >
              Reject
            </Button>
            <Button
              variant="ghost"
              className="w-full"
              onClick={() => navigate("/")}
              icon={<RotateCcw size={16} />}
            >
              Start New Analysis
            </Button>
          </div>
        </div>
      </div>
    </Page>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   Report View - Full formatted report
   ═══════════════════════════════════════════════════════════════════════════ */

function ReportView({ report }: { report: string }) {
  if (!report) {
    return (
      <Card className="h-full flex items-center justify-center">
        <p className="text-[var(--color-text-muted)]">No report generated</p>
      </Card>
    );
  }

  return (
    <Card className="h-full overflow-hidden flex flex-col">
      <div className="flex-1 overflow-y-auto">
        <pre className="text-sm text-[var(--color-text-primary)] whitespace-pre-wrap font-mono leading-relaxed p-4">
          {formatReport(report)}
        </pre>
      </div>
    </Card>
  );
}

function formatReport(report: string): string {
  // Clean up the report for display
  return report
    .replace(/═+/g, (match) => "═".repeat(Math.min(match.length, 60)))
    .trim();
}

/* ═══════════════════════════════════════════════════════════════════════════
   Layers View - Collapsible layers
   ═══════════════════════════════════════════════════════════════════════════ */

function LayersView({ 
  report, 
  expandedLayers, 
  toggleLayer 
}: { 
  report: string;
  expandedLayers: Set<number>;
  toggleLayer: (layer: number) => void;
}) {
  const layers = parseReportIntoLayers(report);

  if (layers.length === 0) {
    return (
      <Card className="h-full flex items-center justify-center">
        <p className="text-[var(--color-text-muted)]">No layers found in report</p>
      </Card>
    );
  }

  return (
    <div className="h-full overflow-y-auto space-y-3">
      {layers.map((layer, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.1 }}
        >
          <Card className="overflow-hidden">
            <button
              onClick={() => toggleLayer(i)}
              className="w-full flex items-center gap-3 p-4 text-left hover:bg-[var(--color-bg-hover)] transition-colors"
            >
              {expandedLayers.has(i) ? (
                <ChevronDown size={18} className="text-[var(--color-text-muted)]" />
              ) : (
                <ChevronRight size={18} className="text-[var(--color-text-muted)]" />
              )}
              
              <span className={`px-2 py-0.5 text-xs font-bold rounded ${
                i === 0 ? "bg-[var(--color-error-subtle)] text-[var(--color-error)]" :
                i === 1 ? "bg-[var(--color-warning-subtle)] text-[var(--color-warning)]" :
                "bg-[var(--color-success-subtle)] text-[var(--color-success)]"
              }`}>
                Layer {i}
              </span>
              
              <span className="font-medium text-[var(--color-text-primary)] flex-1">
                {layer.title}
              </span>
            </button>

            {expandedLayers.has(i) && (
              <div className="border-t border-[var(--color-glass-border)] p-4 bg-[var(--color-bg-elevated)]">
                <pre className="text-sm text-[var(--color-text-secondary)] whitespace-pre-wrap font-mono leading-relaxed">
                  {layer.content}
                </pre>
              </div>
            )}
          </Card>
        </motion.div>
      ))}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   Helper functions
   ═══════════════════════════════════════════════════════════════════════════ */

interface ParsedLayer {
  title: string;
  content: string;
}

function parseReportIntoLayers(report: string): ParsedLayer[] {
  const layers: ParsedLayer[] = [];
  
  // Split by LAYER headers
  const layerRegex = /═+\s*\nLAYER\s+(\d+)\s*[—–-]\s*([^\n]+)\n═+/gi;
  const parts = report.split(layerRegex);
  
  // parts: [before, layerNum, title, content, layerNum, title, content, ...]
  for (let i = 1; i < parts.length; i += 3) {
    const layerNum = parts[i];
    const title = parts[i + 1]?.trim() || `Layer ${layerNum}`;
    let content = parts[i + 2] || "";
    
    // Find where the next section starts
    const nextSectionIdx = content.search(/═+\s*\n[A-Z]/);
    if (nextSectionIdx > 0) {
      content = content.substring(0, nextSectionIdx);
    }
    
    layers.push({ title, content: content.trim() });
  }
  
  // If no layers found, try to extract sections differently
  if (layers.length === 0) {
    const sections = report.split(/═{10,}/);
    sections.forEach((section) => {
      const trimmed = section.trim();
      if (trimmed && trimmed.length > 50) {
        const firstLine = trimmed.split("\n")[0];
        layers.push({
          title: firstLine.substring(0, 50) + (firstLine.length > 50 ? "..." : ""),
          content: trimmed
        });
      }
    });
  }
  
  return layers;
}

function countLayers(report: string): number {
  const matches = report.match(/LAYER\s+\d+/gi);
  return matches ? matches.length : 0;
}

function countServices(report: string): number {
  const matches = report.match(/SERVICE:\s*[\w-]+/gi);
  return matches ? new Set(matches).size : 0;
}
