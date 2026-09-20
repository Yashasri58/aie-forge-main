import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  FolderGit2,
  FileCode2,
  GitBranch,
  Globe,
  Link2,
  ChevronRight,
  ChevronLeft,
  Play,
  RotateCcw,
} from "lucide-react";
import { Button } from "./ui";

interface HowItWorksProps {
  open: boolean;
  onClose: () => void;
  stats: {
    services: number;
    symbols: number;
    edges: number;
  };
}

interface Step {
  id: number;
  title: string;
  description: string;
  icon: React.ReactNode;
  visual: React.ReactNode;
  stat?: { value: number; label: string };
}

export default function HowItWorks({ open, onClose, stats }: HowItWorksProps) {
  const [currentStep, setCurrentStep] = useState(0);
  const [autoPlay, setAutoPlay] = useState(false);

  // Service names for animation
  const services = [
    "payment-processor",
    "gateway-service", 
    "account-service",
    "ledger-service",
    "validation-service",
    "fx-service",
    "audit-service",
    "payment-ui",
  ];

  const steps: Step[] = [
    {
      id: 0,
      title: "Scan Microservices",
      description: "Forge discovers and indexes all repositories in your microservices architecture.",
      icon: <FolderGit2 size={24} />,
      stat: { value: stats.services, label: "Repositories" },
      visual: (
        <div className="relative h-48 flex items-center justify-center">
          <div className="grid grid-cols-4 gap-3">
            {services.map((name, i) => (
              <motion.div
                key={name}
                initial={{ opacity: 0, scale: 0 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: i * 0.1, type: "spring", stiffness: 200 }}
                className="flex flex-col items-center gap-2"
              >
                <div className="w-12 h-12 rounded-lg bg-[var(--color-accent-subtle)] border border-[var(--color-accent)] flex items-center justify-center">
                  <FolderGit2 size={20} className="text-[var(--color-accent)]" />
                </div>
                <span className="text-[10px] text-[var(--color-text-muted)] truncate max-w-[60px]">
                  {name.split("-")[0]}
                </span>
              </motion.div>
            ))}
          </div>
        </div>
      ),
    },
    {
      id: 1,
      title: "Extract Symbols",
      description: "Parse each service using codegraph-tools (tree-sitter AST) to extract functions, classes, and their relationships.",
      icon: <FileCode2 size={24} />,
      stat: { value: stats.symbols, label: "Functions" },
      visual: (
        <div className="relative h-48 flex items-center justify-center">
          <div className="flex items-center gap-8">
            {/* Service box */}
            <motion.div
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              className="w-20 h-20 rounded-lg bg-[var(--color-accent-subtle)] border border-[var(--color-accent)] flex items-center justify-center"
            >
              <FolderGit2 size={28} className="text-[var(--color-accent)]" />
            </motion.div>

            {/* Arrow with functions flowing */}
            <div className="relative w-32 h-20">
              <motion.div
                initial={{ scaleX: 0 }}
                animate={{ scaleX: 1 }}
                transition={{ delay: 0.3 }}
                className="absolute top-1/2 left-0 right-0 h-0.5 bg-[var(--color-accent)] origin-left"
              />
              {[0, 1, 2, 3, 4].map((i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, x: 0 }}
                  animate={{ opacity: [0, 1, 1, 0], x: [0, 60, 120, 140] }}
                  transition={{
                    delay: 0.5 + i * 0.2,
                    duration: 1,
                    repeat: Infinity,
                    repeatDelay: 0.8,
                  }}
                  className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-[var(--color-accent)]"
                  style={{ top: `${30 + (i % 3) * 20}%` }}
                />
              ))}
            </div>

            {/* Extracted symbols */}
            <motion.div
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.6 }}
              className="flex flex-col gap-1"
            >
              {["processPayment()", "validateCard()", "createOrder()", "logEvent()"].map((fn, i) => (
                <motion.div
                  key={fn}
                  initial={{ opacity: 0, x: 10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.8 + i * 0.15 }}
                  className="px-2 py-1 rounded bg-[var(--color-bg-elevated)] border border-[var(--color-glass-border)] text-xs font-mono text-[var(--color-accent)]"
                >
                  {fn}
                </motion.div>
              ))}
            </motion.div>
          </div>
        </div>
      ),
    },
    {
      id: 2,
      title: "Map Internal Calls",
      description: "Trace function-to-function call relationships within each service.",
      icon: <GitBranch size={24} />,
      visual: (
        <div className="relative h-48 flex items-center justify-center">
          <svg width="280" height="160" className="overflow-visible">
            {/* Nodes */}
            {[
              { x: 60, y: 40, label: "main()" },
              { x: 180, y: 40, label: "init()" },
              { x: 40, y: 100, label: "process()" },
              { x: 140, y: 100, label: "validate()" },
              { x: 240, y: 100, label: "save()" },
              { x: 90, y: 140, label: "log()" },
            ].map((node, i) => (
              <motion.g key={i}>
                <motion.circle
                  cx={node.x}
                  cy={node.y}
                  r="20"
                  fill="var(--color-accent-subtle)"
                  stroke="var(--color-accent)"
                  strokeWidth="2"
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{ delay: i * 0.1, type: "spring" }}
                />
                <motion.text
                  x={node.x}
                  y={node.y + 35}
                  textAnchor="middle"
                  fill="var(--color-text-secondary)"
                  fontSize="10"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: i * 0.1 + 0.2 }}
                >
                  {node.label}
                </motion.text>
              </motion.g>
            ))}
            
            {/* Edges */}
            {[
              { x1: 75, y1: 55, x2: 55, y2: 85 },
              { x1: 75, y1: 50, x2: 125, y2: 90 },
              { x1: 195, y1: 55, x2: 225, y2: 85 },
              { x1: 155, y1: 110, x2: 105, y2: 130 },
              { x1: 55, y1: 115, x2: 75, y2: 130 },
            ].map((edge, i) => (
              <motion.line
                key={i}
                x1={edge.x1}
                y1={edge.y1}
                x2={edge.x2}
                y2={edge.y2}
                stroke="var(--color-accent)"
                strokeWidth="2"
                initial={{ pathLength: 0, opacity: 0 }}
                animate={{ pathLength: 1, opacity: 0.6 }}
                transition={{ delay: 0.6 + i * 0.1, duration: 0.3 }}
              />
            ))}
          </svg>
        </div>
      ),
    },
    {
      id: 3,
      title: "Detect HTTP Routes",
      description: "Identify REST endpoints, Express routes, and HTTP client calls including template literals like `${SERVICE_URL}/path`.",
      icon: <Globe size={24} />,
      visual: (
        <div className="relative h-48 flex items-center justify-center">
          <div className="grid grid-cols-2 gap-4">
            {[
              { service: "payment", routes: ["POST /payments", "GET /payments/:id"] },
              { service: "account", routes: ["GET /accounts", "POST /accounts/lookup"] },
              { service: "gateway", routes: ["POST /api/pay", "GET /api/status"] },
              { service: "ledger", routes: ["POST /entries", "GET /balance"] },
            ].map((svc, i) => (
              <motion.div
                key={svc.service}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.15 }}
                className="p-3 rounded-lg bg-[var(--color-bg-elevated)] border border-[var(--color-glass-border)]"
              >
                <div className="text-xs font-medium text-[var(--color-text-primary)] mb-2">
                  {svc.service}-service
                </div>
                {svc.routes.map((route, j) => (
                  <motion.div
                    key={route}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.15 + j * 0.1 + 0.3 }}
                    className="text-[10px] font-mono text-[var(--color-accent)] flex items-center gap-1"
                  >
                    <Globe size={10} className="opacity-50" />
                    {route}
                  </motion.div>
                ))}
              </motion.div>
            ))}
          </div>
        </div>
      ),
    },
    {
      id: 4,
      title: "Link Cross-Service",
      description: "Store the unified dependency graph in Kuzu database, enabling Cypher queries for impact analysis.",
      icon: <Link2 size={24} />,
      stat: { value: stats.edges, label: "Connections" },
      visual: (
        <div className="relative h-48 flex items-center justify-center">
          <svg width="320" height="180" className="overflow-visible">
            {/* Service nodes in a circle */}
            {services.slice(0, 6).map((name, i) => {
              const angle = (i * 60 - 90) * (Math.PI / 180);
              const x = 160 + Math.cos(angle) * 70;
              const y = 90 + Math.sin(angle) * 60;
              return (
                <motion.g key={name}>
                  <motion.circle
                    cx={x}
                    cy={y}
                    r="25"
                    fill="var(--color-accent-subtle)"
                    stroke="var(--color-accent)"
                    strokeWidth="2"
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    transition={{ delay: i * 0.1, type: "spring" }}
                  />
                  <motion.text
                    x={x}
                    y={y + 4}
                    textAnchor="middle"
                    fill="var(--color-text-primary)"
                    fontSize="8"
                    fontWeight="500"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: i * 0.1 + 0.2 }}
                  >
                    {name.split("-")[0]}
                  </motion.text>
                </motion.g>
              );
            })}
            
            {/* Animated HTTP connections */}
            {[
              { from: 0, to: 2 }, // payment -> account
              { from: 0, to: 3 }, // payment -> ledger
              { from: 1, to: 0 }, // gateway -> payment
              { from: 0, to: 4 }, // payment -> validation
              { from: 0, to: 5 }, // payment -> fx
            ].map((edge, i) => {
              const fromAngle = (edge.from * 60 - 90) * (Math.PI / 180);
              const toAngle = (edge.to * 60 - 90) * (Math.PI / 180);
              const x1 = 160 + Math.cos(fromAngle) * 70;
              const y1 = 90 + Math.sin(fromAngle) * 60;
              const x2 = 160 + Math.cos(toAngle) * 70;
              const y2 = 90 + Math.sin(toAngle) * 60;
              
              return (
                <motion.g key={i}>
                  <motion.line
                    x1={x1}
                    y1={y1}
                    x2={x2}
                    y2={y2}
                    stroke="var(--color-accent)"
                    strokeWidth="2"
                    strokeDasharray="4 2"
                    initial={{ pathLength: 0, opacity: 0 }}
                    animate={{ pathLength: 1, opacity: 0.6 }}
                    transition={{ delay: 0.8 + i * 0.15, duration: 0.4 }}
                  />
                  {/* Animated dot traveling along the line */}
                  <motion.circle
                    cx={x1}
                    cy={y1}
                    r="3"
                    fill="var(--color-accent)"
                    initial={{ opacity: 0 }}
                    animate={{
                      opacity: [0, 1, 1, 0],
                      cx: [x1, x2],
                      cy: [y1, y2],
                    }}
                    transition={{
                      delay: 1.2 + i * 0.2,
                      duration: 0.8,
                      repeat: Infinity,
                      repeatDelay: 1.5,
                    }}
                  />
                </motion.g>
              );
            })}
          </svg>
        </div>
      ),
    },
  ];

  // Auto-advance steps
  useEffect(() => {
    if (!autoPlay || !open) return;
    
    const timer = setInterval(() => {
      setCurrentStep((prev) => {
        if (prev >= steps.length - 1) {
          setAutoPlay(false);
          return prev;
        }
        return prev + 1;
      });
    }, 3000);
    
    return () => clearInterval(timer);
  }, [autoPlay, open, steps.length]);

  // Reset on open
  useEffect(() => {
    if (open) {
      setCurrentStep(0);
      setAutoPlay(false);
    }
  }, [open]);

  if (!open) return null;

  const step = steps[currentStep];

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center p-4"
        onClick={onClose}
      >
        {/* Backdrop */}
        <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />

        {/* Modal */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 20 }}
          onClick={(e) => e.stopPropagation()}
          className="relative w-full max-w-2xl bg-[var(--color-bg-surface)] border border-[var(--color-glass-border)] rounded-2xl shadow-2xl overflow-hidden"
        >
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b border-[var(--color-glass-border)]">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-[var(--color-accent-subtle)] flex items-center justify-center">
                <Link2 size={20} className="text-[var(--color-accent)]" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">
                  How the Code Graph Works
                </h2>
                <p className="text-sm text-[var(--color-text-muted)]">
                  Multi-repo dependency analysis
                </p>
              </div>
            </div>
            <button
              onClick={onClose}
              className="p-2 rounded-lg hover:bg-[var(--color-bg-elevated)] transition-colors"
            >
              <X size={20} className="text-[var(--color-text-muted)]" />
            </button>
          </div>

          {/* Step Progress */}
          <div className="px-6 pt-4">
            <div className="flex items-center gap-2">
              {steps.map((s, i) => (
                <button
                  key={s.id}
                  onClick={() => setCurrentStep(i)}
                  className={`flex-1 h-1.5 rounded-full transition-all ${
                    i === currentStep
                      ? "bg-[var(--color-accent)]"
                      : i < currentStep
                      ? "bg-[var(--color-accent)]/50"
                      : "bg-[var(--color-glass-border)]"
                  }`}
                />
              ))}
            </div>
            <div className="flex items-center justify-between mt-2">
              <span className="text-xs text-[var(--color-text-muted)]">
                Step {currentStep + 1} of {steps.length}
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => {
                    setCurrentStep(0);
                    setAutoPlay(true);
                  }}
                  className="text-xs text-[var(--color-accent)] hover:underline flex items-center gap-1"
                >
                  {autoPlay ? (
                    <>
                      <RotateCcw size={12} /> Playing...
                    </>
                  ) : (
                    <>
                      <Play size={12} /> Auto-play
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>

          {/* Content */}
          <div className="p-6">
            <AnimatePresence mode="wait">
              <motion.div
                key={step.id}
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.2 }}
              >
                {/* Step Header */}
                <div className="flex items-start gap-4 mb-6">
                  <div className="w-12 h-12 rounded-xl bg-[var(--color-accent-subtle)] flex items-center justify-center text-[var(--color-accent)] flex-shrink-0">
                    {step.icon}
                  </div>
                  <div className="flex-1">
                    <h3 className="text-xl font-semibold text-[var(--color-text-primary)] mb-1">
                      {step.title}
                    </h3>
                    <p className="text-sm text-[var(--color-text-secondary)]">
                      {step.description}
                    </p>
                  </div>
                  {step.stat && (
                    <div className="text-right">
                      <div className="text-2xl font-bold text-[var(--color-accent)]">
                        {step.stat.value}
                      </div>
                      <div className="text-xs text-[var(--color-text-muted)]">
                        {step.stat.label}
                      </div>
                    </div>
                  )}
                </div>

                {/* Visual */}
                <div className="bg-[var(--color-bg-base)] rounded-xl border border-[var(--color-glass-border)] overflow-hidden">
                  {step.visual}
                </div>
              </motion.div>
            </AnimatePresence>
          </div>

          {/* Footer Navigation */}
          <div className="flex items-center justify-between p-4 border-t border-[var(--color-glass-border)]">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setCurrentStep((p) => Math.max(0, p - 1))}
              disabled={currentStep === 0}
              icon={<ChevronLeft size={16} />}
            >
              Previous
            </Button>

            <div className="flex items-center gap-4 text-sm text-[var(--color-text-muted)]">
              <span>{stats.services} repos</span>
              <span>→</span>
              <span>{stats.symbols} functions</span>
              <span>→</span>
              <span>{stats.edges} connections</span>
            </div>

            <Button
              variant={currentStep === steps.length - 1 ? "primary" : "secondary"}
              size="sm"
              onClick={() => {
                if (currentStep === steps.length - 1) {
                  onClose();
                } else {
                  setCurrentStep((p) => p + 1);
                }
              }}
            >
              {currentStep === steps.length - 1 ? "Got it" : "Next"}
              {currentStep < steps.length - 1 && <ChevronRight size={16} />}
            </Button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
