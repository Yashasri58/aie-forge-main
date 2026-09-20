import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  FileText,
  Search,
  Brain,
  ShieldCheck,
  PenSquare,
  ChevronRight,
  ChevronLeft,
  Upload,
  Layers,
  Tag,
  Download,
} from "lucide-react";
import { Button } from "./ui";

interface HowREWorksProps {
  open: boolean;
  onClose: () => void;
}

interface Step {
  id: number;
  stage: string;
  title: string;
  description: string;
  icon: React.ReactNode;
  detail: string[];
  output: string;
  color: string;
}

const STEPS: Step[] = [
  {
    id: 1,
    stage: "Stage 1",
    title: "Log Parser",
    description: "Deterministic extraction — zero LLM",
    icon: <Upload size={22} />,
    detail: [
      "Reads every line of your log file using regex patterns",
      "Extracts: service names, endpoints, trace/span IDs, Kafka topics, SLO metrics, error events",
      "Builds a structured ExtractedFacts object — this is the ground truth",
      "Runs in milliseconds — no network calls, no AI",
    ],
    output: "16 services · 5 endpoints · 4 trace flows · 1 Kafka topic",
    color: "text-blue-400",
  },
  {
    id: 2,
    stage: "Stage 2",
    title: "Template Extractor",
    description: "drain3 log mining — zero LLM",
    icon: <Layers size={22} />,
    detail: [
      "Runs drain3 (tree-sitter-style log mining) on all log lines",
      "Groups similar lines into templates, replacing variable parts with <*> tokens",
      "Compresses 40 raw lines → 32 unique behavioural patterns",
      "These templates become the evidence base for Stage 3",
    ],
    output: "32 templates extracted from 41 lines",
    color: "text-cyan-400",
  },
  {
    id: 3,
    stage: "Stage 3",
    title: "Inference Agent",
    description: "Gemini 2.5 Pro — 1 LLM call",
    icon: <Brain size={22} />,
    detail: [
      "Receives the ExtractedFacts + your user context as supplementary hints",
      "Builds an Application Specification Graph (ASG) with service nodes, dependency edges, and claims",
      "Tags every claim: CONFIRMED (direct log evidence) / INFERRED (deduced) / GAP (not observable)",
      "Harness: budget enforcer, loop detector, input sanitizer, hallucinated service name grounder",
    ],
    output: "15 CONFIRMED · 1 INFERRED · 4 GAP — 75% grounded",
    color: "text-purple-400",
  },
  {
    id: 4,
    stage: "Stage 4",
    title: "Gap Agent",
    description: "Gemini 2.5 Flash — review pass",
    icon: <ShieldCheck size={22} />,
    detail: [
      "Reviews the ASG produced by Stage 3",
      "Downgrades over-confident CONFIRMED claims to INFERRED when evidence is insufficient",
      "Identifies true GAPs — things that are simply not observable from log data alone",
      "Each reclassification is logged with the old confidence, new confidence, and reason",
    ],
    output: "19 reclassifications · 8 gaps · confidence=MEDIUM",
    color: "text-orange-400",
  },
  {
    id: 5,
    stage: "Stage 5",
    title: "Spec Writer",
    description: "Gemini 2.5 Flash — 12 sections",
    icon: <PenSquare size={22} />,
    detail: [
      "Generates 12 Markdown specification sections from the verified ASG",
      "Each section is one LLM call: Executive Summary, Service Inventory, API Catalog, Business Logic, Event Topology, Data Model, Cross-Cutting, SLOs, Resilience, Tech Stack, Risks & Gaps, Confidence Report",
      "Retries once per section on failure (budget: 15 calls for 12 sections)",
      "Inline CONFIRMED / INFERRED / GAP badges carried through to the final Markdown",
    ],
    output: "12/12 sections · ~60,000 chars total · ZIP download",
    color: "text-green-400",
  },
];

export default function HowREWorks({ open, onClose }: HowREWorksProps) {
  const [currentStep, setCurrentStep] = useState(0);

  const step = STEPS[currentStep];

  if (!open) return null;

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          {/* Backdrop */}
          <motion.div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={onClose}
          />

          {/* Modal */}
          <motion.div
            className="relative w-full max-w-2xl bg-[var(--color-surface)] border border-[var(--color-glass-border)] rounded-2xl shadow-2xl overflow-hidden"
            initial={{ scale: 0.95, opacity: 0, y: 20 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.95, opacity: 0, y: 20 }}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--color-glass-border)]">
              <div className="flex items-center gap-3">
                <Search size={18} className="text-[var(--color-accent)]" />
                <div>
                  <h2 className="text-base font-semibold text-[var(--color-text-primary)]">
                    How Reverse Engineer Works
                  </h2>
                  <p className="text-xs text-[var(--color-text-muted)]">
                    Log file → 12-section spec, no source code needed
                  </p>
                </div>
              </div>
              <button
                onClick={onClose}
                className="p-1.5 rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-glass-bg)] transition-colors"
              >
                <X size={18} />
              </button>
            </div>

            {/* Stage progress */}
            <div className="flex items-center gap-1 px-6 py-3 border-b border-[var(--color-glass-border)] bg-[var(--color-glass-bg)]">
              {STEPS.map((s, i) => (
                <button
                  key={s.id}
                  onClick={() => setCurrentStep(i)}
                  className={`flex-1 h-1.5 rounded-full transition-all ${
                    i === currentStep
                      ? "bg-[var(--color-accent)]"
                      : i < currentStep
                      ? "bg-[var(--color-accent)]/40"
                      : "bg-[var(--color-glass-border)]"
                  }`}
                />
              ))}
            </div>

            {/* Step content */}
            <AnimatePresence mode="wait">
              <motion.div
                key={currentStep}
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.2 }}
                className="p-6"
              >
                {/* Stage header */}
                <div className="flex items-start gap-4 mb-5">
                  <div className={`p-2.5 rounded-xl bg-[var(--color-glass-bg)] border border-[var(--color-glass-border)] ${step.color}`}>
                    {step.icon}
                  </div>
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs font-mono text-[var(--color-text-muted)] uppercase tracking-wider">
                        {step.stage}
                      </span>
                    </div>
                    <h3 className="text-lg font-semibold text-[var(--color-text-primary)]">
                      {step.title}
                    </h3>
                    <p className="text-sm text-[var(--color-text-muted)]">{step.description}</p>
                  </div>
                </div>

                {/* Detail bullets */}
                <ul className="space-y-2.5 mb-5">
                  {step.detail.map((d, i) => (
                    <li key={i} className="flex items-start gap-3 text-sm text-[var(--color-text-secondary)]">
                      <span className={`mt-0.5 shrink-0 ${step.color}`}>
                        <ChevronRight size={14} />
                      </span>
                      {d}
                    </li>
                  ))}
                </ul>

                {/* Output example */}
                <div className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[var(--color-glass-bg)] border border-[var(--color-glass-border)]">
                  <Tag size={13} className="text-[var(--color-accent)] shrink-0" />
                  <span className="text-xs font-mono text-[var(--color-text-muted)]">Example output:</span>
                  <span className="text-xs font-mono text-[var(--color-text-primary)]">{step.output}</span>
                </div>
              </motion.div>
            </AnimatePresence>

            {/* Footer */}
            <div className="flex items-center justify-between px-6 py-4 border-t border-[var(--color-glass-border)] bg-[var(--color-glass-bg)]">
              <div className="flex items-center gap-2">
                <FileText size={13} className="text-[var(--color-text-muted)]" />
                <span className="text-xs text-[var(--color-text-muted)]">
                  {currentStep + 1} / {STEPS.length}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setCurrentStep((p) => Math.max(0, p - 1))}
                  disabled={currentStep === 0}
                  icon={<ChevronLeft size={15} />}
                >
                  Back
                </Button>
                {currentStep < STEPS.length - 1 ? (
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => setCurrentStep((p) => p + 1)}
                    icon={<ChevronRight size={15} />}
                  >
                    Next
                  </Button>
                ) : (
                  <Button variant="primary" size="sm" onClick={onClose} icon={<Download size={15} />}>
                    Got it — Upload Logs
                  </Button>
                )}
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
