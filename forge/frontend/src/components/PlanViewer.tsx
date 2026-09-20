import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileCode,
  GitBranch,
  Layers,
  ChevronDown,
  ChevronRight,
  AlertTriangle,
  Lightbulb,
  Code2,
} from "lucide-react";
import type { CodeGenPlan, CodeGenTask, CodeGenContract, ExecutionPhase } from "../types";

interface PlanViewerProps {
  plan: CodeGenPlan;
}

export function PlanViewer({ plan }: PlanViewerProps) {
  const [expandedSections, setExpandedSections] = useState<Set<string>>(
    new Set(["analysis", "execution"])
  );

  const toggleSection = (section: string) => {
    setExpandedSections((prev) => {
      const next = new Set(prev);
      if (next.has(section)) {
        next.delete(section);
      } else {
        next.add(section);
      }
      return next;
    });
  };

  return (
    <div className="space-y-4">
      {/* Analysis Section */}
      {plan.analysis && (
        <Section
          id="analysis"
          title="Analysis"
          icon={<Lightbulb size={16} />}
          expanded={expandedSections.has("analysis")}
          onToggle={() => toggleSection("analysis")}
        >
          <div className="space-y-4">
            {/* Summary */}
            <div>
              <h4 className="text-xs font-medium text-[var(--color-text-muted)] uppercase mb-2">
                Summary
              </h4>
              <p className="text-sm text-[var(--color-text-primary)]">
                {plan.analysis.summary}
              </p>
            </div>

            {/* Reasoning */}
            {plan.analysis.reasoning && (
              <div>
                <h4 className="text-xs font-medium text-[var(--color-text-muted)] uppercase mb-2">
                  Reasoning
                </h4>
                <p className="text-sm text-[var(--color-text-secondary)]">
                  {plan.analysis.reasoning}
                </p>
              </div>
            )}

            {/* Risks */}
            {plan.analysis.risks && plan.analysis.risks.length > 0 && (
              <div>
                <h4 className="text-xs font-medium text-[var(--color-text-muted)] uppercase mb-2 flex items-center gap-2">
                  <AlertTriangle size={12} className="text-[var(--color-warning)]" />
                  Risks
                </h4>
                <ul className="space-y-1">
                  {plan.analysis.risks.map((risk, i) => (
                    <li
                      key={i}
                      className="text-sm text-[var(--color-text-secondary)] flex items-start gap-2"
                    >
                      <span className="text-[var(--color-warning)]">•</span>
                      {risk}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Existing Patterns */}
            {plan.analysis.existing_patterns && plan.analysis.existing_patterns.length > 0 && (
              <div>
                <h4 className="text-xs font-medium text-[var(--color-text-muted)] uppercase mb-2">
                  Existing Patterns
                </h4>
                <div className="space-y-2">
                  {plan.analysis.existing_patterns.map((pattern, i) => (
                    <div
                      key={i}
                      className="p-2 rounded bg-[var(--color-bg-elevated)] text-sm"
                    >
                      <div className="flex items-center justify-between">
                        <code className="text-[var(--color-accent)]">{pattern.pattern}</code>
                        {pattern.reuse && (
                          <span className="text-xs px-2 py-0.5 rounded bg-[var(--color-success-subtle)] text-[var(--color-success)]">
                            Reuse
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-[var(--color-text-muted)] mt-1">
                        {pattern.location}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </Section>
      )}

      {/* Design Decisions */}
      {plan.design && (
        <Section
          id="design"
          title="Design Decisions"
          icon={<GitBranch size={16} />}
          expanded={expandedSections.has("design")}
          onToggle={() => toggleSection("design")}
        >
          <div className="space-y-3">
            {plan.design.decisions.map((decision, i) => (
              <div
                key={i}
                className="p-3 rounded bg-[var(--color-bg-elevated)] border-l-2 border-[var(--color-accent)]"
              >
                <p className="text-sm font-medium text-[var(--color-text-primary)]">
                  {decision.decision}
                </p>
                <p className="text-xs text-[var(--color-text-muted)] mt-1">
                  {decision.rationale}
                </p>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Contracts */}
      {plan.contracts && Object.keys(plan.contracts).length > 0 && (
        <Section
          id="contracts"
          title={`Contracts (${Object.keys(plan.contracts).length})`}
          icon={<Code2 size={16} />}
          expanded={expandedSections.has("contracts")}
          onToggle={() => toggleSection("contracts")}
        >
          <div className="space-y-3">
            {Object.entries(plan.contracts).map(([name, contract]) => (
              <ContractCard key={name} name={name} contract={contract} />
            ))}
          </div>
        </Section>
      )}

      {/* Execution Plan */}
      <Section
        id="execution"
        title={`Execution Plan (${plan.execution?.length || 0} phases)`}
        icon={<Layers size={16} />}
        expanded={expandedSections.has("execution")}
        onToggle={() => toggleSection("execution")}
      >
        <div className="space-y-4">
          {plan.execution?.map((phase, i) => (
            <PhaseCard
              key={i}
              phase={phase}
              tasks={plan.tasks}
              isFirst={i === 0}
            />
          ))}
        </div>
      </Section>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   Sub-components
   ═══════════════════════════════════════════════════════════════════════════ */

function Section({
  title,
  icon,
  expanded,
  onToggle,
  children,
}: {
  id: string;
  title: string;
  icon: React.ReactNode;
  expanded: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-[var(--color-glass-border)] overflow-hidden bg-[var(--color-bg-primary)]">
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-3 px-4 py-3 bg-[var(--color-bg-elevated)] hover:bg-[var(--color-bg-hover)] transition-colors text-left"
      >
        {expanded ? (
          <ChevronDown size={16} className="text-[var(--color-text-muted)]" />
        ) : (
          <ChevronRight size={16} className="text-[var(--color-text-muted)]" />
        )}
        <span className="text-[var(--color-accent)]">{icon}</span>
        <span className="font-medium text-[var(--color-text-primary)]">{title}</span>
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="px-4 py-4"
          >
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function ContractCard({ name, contract }: { name: string; contract: CodeGenContract }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded border border-[var(--color-glass-border)] overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-[var(--color-bg-hover)] transition-colors text-left"
      >
        {expanded ? (
          <ChevronDown size={14} className="text-[var(--color-text-muted)]" />
        ) : (
          <ChevronRight size={14} className="text-[var(--color-text-muted)]" />
        )}
        <code className="text-sm text-[var(--color-accent)]">{name}</code>
        <span className="text-xs px-2 py-0.5 rounded bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)]">
          {contract.type}
        </span>
        {contract.is_new && (
          <span className="text-xs px-2 py-0.5 rounded bg-[var(--color-success-subtle)] text-[var(--color-success)]">
            New
          </span>
        )}
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0 }}
            animate={{ height: "auto" }}
            exit={{ height: 0 }}
            className="border-t border-[var(--color-glass-border)] bg-[var(--color-bg-elevated)]"
          >
            <div className="p-3 space-y-3">
              {/* Signature */}
              <div>
                <div className="text-xs text-[var(--color-text-muted)] mb-1">Signature</div>
                <pre className="text-xs bg-[var(--color-bg-primary)] p-2 rounded overflow-x-auto">
                  <code className="text-[var(--color-text-primary)]">{contract.signature}</code>
                </pre>
              </div>

              {/* Implementation */}
              {contract.implementation && (
                <div>
                  <div className="text-xs text-[var(--color-text-muted)] mb-1">Implementation</div>
                  <pre className="text-xs bg-[var(--color-bg-primary)] p-2 rounded overflow-x-auto max-h-40">
                    <code className="text-[var(--color-text-secondary)]">
                      {contract.implementation}
                    </code>
                  </pre>
                </div>
              )}

              {/* Used by */}
              {contract.used_by && contract.used_by.length > 0 && (
                <div>
                  <div className="text-xs text-[var(--color-text-muted)] mb-1">Used by</div>
                  <div className="flex flex-wrap gap-1">
                    {contract.used_by.map((file, i) => (
                      <span
                        key={i}
                        className="text-xs px-2 py-0.5 rounded bg-[var(--color-bg-primary)] text-[var(--color-text-secondary)]"
                      >
                        {file}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function PhaseCard({
  phase,
  tasks,
  isFirst,
}: {
  phase: ExecutionPhase;
  tasks: Record<string, CodeGenTask>;
  isFirst: boolean;
}) {
  return (
    <div className="relative">
      {/* Phase connector line */}
      {!isFirst && (
        <div className="absolute left-4 -top-4 h-4 w-0.5 bg-[var(--color-glass-border)]" />
      )}

      <div className="flex items-start gap-3">
        {/* Phase indicator */}
        <div
          className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold ${
            phase.phase === 0
              ? "bg-[var(--color-accent)] text-white"
              : "bg-[var(--color-bg-elevated)] text-[var(--color-text-primary)] border border-[var(--color-glass-border)]"
          }`}
        >
          {phase.phase}
        </div>

        {/* Phase content */}
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <span className="font-medium text-[var(--color-text-primary)]">
              {phase.description}
            </span>
            {phase.parallel && (
              <span className="text-xs px-2 py-0.5 rounded bg-[var(--color-accent-subtle)] text-[var(--color-accent)]">
                Parallel
              </span>
            )}
          </div>

          {/* Tasks in this phase */}
          <div className="space-y-2">
            {phase.tasks.map((taskId) => {
              const task = tasks[taskId];
              if (!task) return null;

              return (
                <div
                  key={taskId}
                  className="flex items-center gap-2 p-2 rounded bg-[var(--color-bg-elevated)] text-sm"
                >
                  <FileCode size={14} className="text-[var(--color-text-muted)]" />
                  <span className="text-[var(--color-text-primary)] font-mono text-xs flex-1 truncate">
                    {task.file}
                  </span>
                  <span
                    className={`text-xs px-2 py-0.5 rounded ${
                      task.action === "create"
                        ? "bg-[var(--color-success-subtle)] text-[var(--color-success)]"
                        : task.action === "delete"
                        ? "bg-[var(--color-error-subtle)] text-[var(--color-error)]"
                        : "bg-[var(--color-warning-subtle)] text-[var(--color-warning)]"
                    }`}
                  >
                    {task.action}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

export default PlanViewer;
