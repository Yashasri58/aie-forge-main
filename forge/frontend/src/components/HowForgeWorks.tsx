import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  MessageSquare,
  FileCode2,
  GitBranch,
  CheckCircle2,
  Code2,
  FileCheck,
  Users,
  ChevronRight,
  ChevronLeft,
  Play,
  RotateCcw,
  Sparkles,
  GitPullRequest,
  Bot,
  Workflow,
  Wrench,
  Target,
  Zap,
} from "lucide-react";
import { Button } from "./ui";

interface HowForgeWorksProps {
  open: boolean;
  onClose: () => void;
}

interface Step {
  id: number;
  phase: string;
  title: string;
  description: string;
  icon: React.ReactNode;
  agent?: string;
  visual: React.ReactNode;
}

interface AgentDetail {
  name: string;
  role: string;
  goal: string;
  howItWorks: string[];
  tools: { name: string; description: string }[];
  input: string;
  output: string;
}

const AGENT_DETAILS: Record<string, AgentDetail> = {
  "Context Gatherer Agent": {
    name: "Context Gatherer Agent",
    role: "Requirements Clarification",
    goal: "Understand exactly what the user wants to build or modify by asking targeted clarifying questions and proactively warning about high-impact changes.",
    howItWorks: [
      "Receives vague user requirement",
      "Queries code graph to find relevant services and functions",
      "Checks impact of mentioned functions (caller count, risk level)",
      "Shows service dependencies to give context",
      "Warns about critical services or high-impact changes",
      "Asks clarifying questions about scope and constraints",
      "Confirms understanding before proceeding"
    ],
    tools: [
      { name: "get_available_services()", description: "List all indexed microservices" },
      { name: "search_functions(query, service)", description: "Find functions by name pattern" },
      { name: "get_function_impact_summary(name)", description: "Get caller count, affected services, risk level" },
      { name: "get_service_overview(service)", description: "Get function count, HTTP dependencies, criticality" }
    ],
    input: "Natural language requirement from user",
    output: "Structured RequirementsOutput (services, functions, description, constraints)"
  },
  "Impact Agent": {
    name: "Impact Agent",
    role: "Dependency Analysis",
    goal: "Answer 'What breaks if I change X?' by tracing all call paths and cross-service dependencies.",
    howItWorks: [
      "Queries Kuzu graph database using Cypher",
      "Traces callers (who calls this function?)",
      "Traces callees (what does this function call?)",
      "Identifies cross-service HTTP dependencies",
      "Produces layered impact report (Layer 0, 1, 2)"
    ],
    tools: [
      { name: "analyze_impact(symbol)", description: "Full impact analysis with risk assessment" },
      { name: "trace_call_path(symbol, direction, depth)", description: "Follow call chains in/out" },
      { name: "search_symbols(query, kind, service)", description: "Find symbols by name" },
      { name: "get_service_topology(service)", description: "HTTP dependencies between services" },
      { name: "query_graph(cypher)", description: "Raw Cypher query for complex analysis" },
      { name: "get_schema()", description: "Graph schema for context" }
    ],
    input: "Confirmed requirements from Context Gatherer",
    output: "Layered impact report with affected files, services, and execution order"
  },
  "Verification Agent": {
    name: "Verification Agent",
    role: "Completeness Check",
    goal: "Ensure impact analysis is complete — all call paths traced, cross-service HTTP deps captured, no dependencies missed.",
    howItWorks: [
      "Reviews impact report from Impact Agent",
      "Verifies all callers are traced at each layer using trace_callers()",
      "Checks cross-service HTTP dependencies via get_service_http_calls()",
      "Uses get_symbol_context() to verify symbols are in correct service/file",
      "Identifies gaps and triggers re-analysis if needed",
      "Loops with Impact Agent up to 3 times until complete"
    ],
    tools: [
      { name: "trace_callers(symbol, max_depth)", description: "Verify all callers are found" },
      { name: "trace_callees(symbol, max_depth)", description: "Verify all callees are found" },
      { name: "search_symbol(name)", description: "Find specific symbols to verify" },
      { name: "get_symbol_context(symbol_name)", description: "Get full context — file, service, callers for accuracy check" },
      { name: "get_service_http_calls(service)", description: "Verify cross-service HTTP dependencies are captured" }
    ],
    input: "Impact report from Impact Agent",
    output: "Verification result: {complete: bool, confidence: %, gaps: []}"
  },
  "Design Agent": {
    name: "Design Agent",
    role: "Plan Creation",
    goal: "Create a complete, unambiguous plan.json that implementation agents can follow WITHOUT any additional context.",
    howItWorks: [
      "Reads impact report and understands required changes",
      "Calls get_similar_patterns() FIRST to reuse existing code (retry, error handling, etc.)",
      "Calls get_http_topology() for any cross-service change to understand dependencies",
      "Calls find_tests() to discover existing tests that must be updated",
      "Explores codebase structure using list_directory()",
      "Verifies target files exist before planning modifications",
      "Defines contracts (interfaces) for shared code",
      "Specifies exact code changes with before/after",
      "Determines execution phases and dependencies"
    ],
    tools: [
      { name: "get_similar_patterns(type, service)", description: "Find existing patterns to reuse (retry, error_handling, logging, http_client, etc.)" },
      { name: "get_http_topology()", description: "Full HTTP dependency map between services" },
      { name: "find_tests(symbol_or_file)", description: "Find test files for a symbol — ensures test updates are included in plan" },
      { name: "query_code_graph(type, service, file, symbol)", description: "Query symbols, calls, HTTP connections" },
      { name: "read_file(path)", description: "Read any file in the codebase" },
      { name: "grep(pattern, file_glob)", description: "Search for patterns across codebase" },
      { name: "list_directory(path, recursive)", description: "Explore directory structure" }
    ],
    input: "Approved impact report",
    output: "Detailed plan.json with tasks, contracts, phases, and exact code"
  },
  "Coordinator Agent": {
    name: "Coordinator Agent",
    role: "Plan Validation",
    goal: "Validate execution plan before implementation begins — catch issues early to prevent wasted effort.",
    howItWorks: [
      "Checks MODIFY targets exist, CREATE parent dirs exist",
      "Detects circular dependencies in task graph",
      "Validates all contract signatures are correct",
      "Ensures parallel phases don't have conflicts",
      "Verifies import paths will resolve after changes"
    ],
    tools: [
      { name: "check_file_exists(path)", description: "Verify file exists" },
      { name: "check_directory_exists(path)", description: "Verify directory exists" },
      { name: "validate_js_syntax(content)", description: "Check JavaScript syntax" },
      { name: "detect_circular_deps(tasks)", description: "Find circular dependencies" },
      { name: "parse_imports(file_path)", description: "Extract imports from file" },
      { name: "resolve_import_path(from, import)", description: "Verify import resolves" }
    ],
    input: "plan.json from Design Agent",
    output: "Validation result: {valid: bool, errors: [], warnings: []}"
  },
  "Implementation Agent(s)": {
    name: "Implementation Agent",
    role: "Code Generation",
    goal: "Execute tasks from plan and generate unified diffs — follow contracts EXACTLY, make ONLY specified changes.",
    howItWorks: [
      "Receives single task with file, action, changes, contracts",
      "Calls read_current_file() to verify live file state before modifying",
      "For MODIFY: reads current content, applies changes precisely",
      "For CREATE: generates complete new file from scratch",
      "Follows contract signatures exactly",
      "Outputs unified diff format",
      "Multiple agents run in parallel (up to 5 per phase)"
    ],
    tools: [
      { name: "read_current_file(file_path)", description: "Read live file content to verify state before implementing — guards against stale task specs" }
    ],
    input: "Task specification with file, action, changes, contracts, conventions",
    output: "Unified diff for the file"
  },
  "Verifier Agent": {
    name: "Verifier Agent",
    role: "Quality Gate",
    goal: "Verify generated diffs EXACTLY match the plan — correct files, contract signatures, all specified changes.",
    howItWorks: [
      "Matches each diff to its task specification",
      "Checks file path matches task.file exactly",
      "Verifies all changes from task.changes are implemented",
      "Confirms no extra changes were added",
      "Validates contract signatures match exactly",
      "Checks syntax, imports, error handling",
      "Returns actionable feedback for retry if issues found"
    ],
    tools: [
      { name: "get_task_from_plan(plan, task_id)", description: "Get task specification" },
      { name: "compare_signature(code, contract)", description: "Verify function matches contract" },
      { name: "parse_diff(diff_text)", description: "Parse diff structure" },
      { name: "check_js_syntax(code)", description: "Validate JavaScript syntax" },
      { name: "find_undefined_references(code)", description: "Find undefined variables" },
      { name: "check_imports_resolve(code, file)", description: "Verify imports resolve" }
    ],
    input: "plan.json + generated diffs",
    output: "Verification result: {passed: bool, issues: [], summary: str}"
  }
};

export default function HowForgeWorks({ open, onClose }: HowForgeWorksProps) {
  const [currentStep, setCurrentStep] = useState(0);
  const [autoPlay, setAutoPlay] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<AgentDetail | null>(null);

  const steps: Step[] = [
    // Phase 1: User Input
    {
      id: 0,
      phase: "Start",
      title: "Describe Your Change",
      description: "Tell Forge what you want to build or modify in natural language. Be as specific or vague as you like.",
      icon: <MessageSquare size={24} />,
      visual: (
        <div className="relative h-56 flex items-center justify-center p-4">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="w-full max-w-md"
          >
            <div className="bg-[var(--color-bg-elevated)] rounded-xl border border-[var(--color-glass-border)] p-4">
              <div className="flex items-center gap-2 mb-3">
                <div className="w-8 h-8 rounded-full bg-[var(--color-accent-subtle)] flex items-center justify-center">
                  <Users size={16} className="text-[var(--color-accent)]" />
                </div>
                <span className="text-sm font-medium text-[var(--color-text-primary)]">You</span>
              </div>
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.3 }}
                className="text-sm text-[var(--color-text-secondary)] leading-relaxed"
              >
                <motion.span
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.5 }}
                >
                  "Add retry logic with exponential backoff to all payment service HTTP calls"
                </motion.span>
              </motion.div>
            </div>
          </motion.div>
        </div>
      ),
    },
    // Phase 2: Context Gathering
    {
      id: 1,
      phase: "Impact Analysis",
      title: "Context Gathering",
      description: "The Context Gatherer Agent asks clarifying questions to understand exactly what you need.",
      icon: <MessageSquare size={24} />,
      agent: "Context Gatherer Agent",
      visual: (
        <div className="relative h-56 flex items-center justify-center p-4">
          <div className="w-full max-w-md space-y-3">
            <motion.div
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              className="bg-[var(--color-bg-elevated)] rounded-xl border border-[var(--color-accent)]/30 p-4"
            >
              <div className="flex items-center gap-2 mb-2">
                <div className="w-8 h-8 rounded-full bg-[var(--color-accent)] flex items-center justify-center">
                  <Bot size={16} className="text-white" />
                </div>
                <span className="text-sm font-medium text-[var(--color-accent)]">Context Gatherer</span>
              </div>
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.4 }}
                className="text-sm text-[var(--color-text-secondary)]"
              >
                "Which services should have retry logic? I found HTTP calls in:
                <div className="mt-2 flex flex-wrap gap-2">
                  {["payment-processor", "gateway-service"].map((svc, i) => (
                    <motion.span
                      key={svc}
                      initial={{ opacity: 0, scale: 0.8 }}
                      animate={{ opacity: 1, scale: 1 }}
                      transition={{ delay: 0.6 + i * 0.1 }}
                      className="px-2 py-1 rounded bg-[var(--color-accent-subtle)] text-xs font-mono text-[var(--color-accent)]"
                    >
                      {svc}
                    </motion.span>
                  ))}
                </div>
              </motion.div>
            </motion.div>
          </div>
        </div>
      ),
    },
    // Phase 3: Impact Analysis
    {
      id: 2,
      phase: "Impact Analysis",
      title: "Trace Dependencies",
      description: "The Impact Agent queries the code graph to find all affected functions, callers, and cross-service dependencies.",
      icon: <GitBranch size={24} />,
      agent: "Impact Agent",
      visual: (
        <div className="relative h-56 flex items-center justify-center">
          <svg width="360" height="200" className="overflow-visible">
            {/* Central node */}
            <motion.g>
              <motion.circle
                cx="180"
                cy="100"
                r="30"
                fill="var(--color-accent)"
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ type: "spring" }}
              />
              <motion.text
                x="180"
                y="105"
                textAnchor="middle"
                fill="white"
                fontSize="10"
                fontWeight="500"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.3 }}
              >
                processPayment
              </motion.text>
            </motion.g>

            {/* Caller nodes */}
            {[
              { x: 60, y: 50, label: "gateway", type: "caller" },
              { x: 60, y: 150, label: "api/pay", type: "caller" },
              { x: 300, y: 50, label: "validate", type: "callee" },
              { x: 300, y: 100, label: "debit", type: "callee" },
              { x: 300, y: 150, label: "audit", type: "callee" },
            ].map((node, i) => (
              <motion.g key={i}>
                <motion.circle
                  cx={node.x}
                  cy={node.y}
                  r="22"
                  fill={node.type === "caller" ? "var(--color-warning-subtle)" : "var(--color-success-subtle)"}
                  stroke={node.type === "caller" ? "var(--color-warning)" : "var(--color-success)"}
                  strokeWidth="2"
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{ delay: 0.3 + i * 0.1, type: "spring" }}
                />
                <motion.text
                  x={node.x}
                  y={node.y + 4}
                  textAnchor="middle"
                  fill="var(--color-text-primary)"
                  fontSize="9"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.5 + i * 0.1 }}
                >
                  {node.label}
                </motion.text>
              </motion.g>
            ))}

            {/* Edges with animated arrows */}
            {[
              { x1: 82, y1: 60, x2: 150, y2: 90, type: "in" },
              { x1: 82, y1: 140, x2: 150, y2: 110, type: "in" },
              { x1: 210, y1: 85, x2: 278, y2: 55, type: "out" },
              { x1: 210, y1: 100, x2: 278, y2: 100, type: "out" },
              { x1: 210, y1: 115, x2: 278, y2: 145, type: "out" },
            ].map((edge, i) => (
              <motion.line
                key={i}
                x1={edge.x1}
                y1={edge.y1}
                x2={edge.x2}
                y2={edge.y2}
                stroke={edge.type === "in" ? "var(--color-warning)" : "var(--color-success)"}
                strokeWidth="2"
                strokeDasharray="4 2"
                initial={{ pathLength: 0, opacity: 0 }}
                animate={{ pathLength: 1, opacity: 0.7 }}
                transition={{ delay: 0.6 + i * 0.1, duration: 0.3 }}
              />
            ))}

            {/* Labels */}
            <motion.text
              x="60"
              y="185"
              textAnchor="middle"
              fill="var(--color-warning)"
              fontSize="10"
              fontWeight="500"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 1 }}
            >
              Callers
            </motion.text>
            <motion.text
              x="300"
              y="185"
              textAnchor="middle"
              fill="var(--color-success)"
              fontSize="10"
              fontWeight="500"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 1 }}
            >
              Callees
            </motion.text>
          </svg>
        </div>
      ),
    },
    // Phase 4: Verification
    {
      id: 3,
      phase: "Impact Analysis",
      title: "Verify Completeness",
      description: "The Verification Agent ensures all call paths are traced and no dependencies are missed.",
      icon: <CheckCircle2 size={24} />,
      agent: "Verification Agent",
      visual: (
        <div className="relative h-56 flex items-center justify-center p-4">
          <div className="w-full max-w-sm">
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="bg-[var(--color-bg-elevated)] rounded-xl border border-[var(--color-glass-border)] p-4"
            >
              <div className="flex items-center gap-2 mb-4">
                <CheckCircle2 size={20} className="text-[var(--color-success)]" />
                <span className="text-sm font-medium text-[var(--color-text-primary)]">Completeness Check</span>
              </div>
              <div className="space-y-2">
                {[
                  { label: "All callers traced", done: true },
                  { label: "Cross-service deps found", done: true },
                  { label: "HTTP routes mapped", done: true },
                  { label: "No gaps detected", done: true },
                ].map((item, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.3 + i * 0.15 }}
                    className="flex items-center gap-2"
                  >
                    <motion.div
                      initial={{ scale: 0 }}
                      animate={{ scale: 1 }}
                      transition={{ delay: 0.5 + i * 0.15, type: "spring" }}
                    >
                      <CheckCircle2 size={14} className="text-[var(--color-success)]" />
                    </motion.div>
                    <span className="text-xs text-[var(--color-text-secondary)]">{item.label}</span>
                  </motion.div>
                ))}
              </div>
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 1.2 }}
                className="mt-4 pt-3 border-t border-[var(--color-glass-border)] flex items-center justify-between"
              >
                <span className="text-xs text-[var(--color-text-muted)]">Confidence</span>
                <span className="text-sm font-medium text-[var(--color-success)]">98%</span>
              </motion.div>
            </motion.div>
          </div>
        </div>
      ),
    },
    // Phase 5: Human Approval (Impact)
    {
      id: 4,
      phase: "Approval Gate",
      title: "Review Impact Report",
      description: "You review the layered impact report showing all affected files, services, and suggested execution order.",
      icon: <FileCheck size={24} />,
      visual: (
        <div className="relative h-56 flex items-center justify-center p-4">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="w-full max-w-md bg-[var(--color-bg-elevated)] rounded-xl border border-[var(--color-glass-border)] overflow-hidden"
          >
            <div className="p-3 border-b border-[var(--color-glass-border)] flex items-center justify-between">
              <span className="text-sm font-medium text-[var(--color-text-primary)]">Impact Report</span>
              <span className="text-xs text-[var(--color-text-muted)]">3 layers</span>
            </div>
            <div className="p-3 space-y-2 max-h-36 overflow-auto">
              {[
                { layer: 0, label: "Direct Changes", files: 2, color: "var(--color-accent)" },
                { layer: 1, label: "Secondary Impact", files: 4, color: "var(--color-warning)" },
                { layer: 2, label: "Tertiary Impact", files: 2, color: "var(--color-text-muted)" },
              ].map((layer, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.3 + i * 0.15 }}
                  className="flex items-center gap-3 p-2 rounded-lg bg-[var(--color-bg-base)]"
                >
                  <div
                    className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold"
                    style={{ backgroundColor: `${layer.color}20`, color: layer.color }}
                  >
                    {layer.layer}
                  </div>
                  <div className="flex-1">
                    <div className="text-xs font-medium text-[var(--color-text-primary)]">{layer.label}</div>
                  </div>
                  <span className="text-xs text-[var(--color-text-muted)]">{layer.files} files</span>
                </motion.div>
              ))}
            </div>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.9 }}
              className="p-3 border-t border-[var(--color-glass-border)] flex gap-2"
            >
              <Button variant="ghost" size="sm" className="flex-1">
                Reject
              </Button>
              <Button variant="primary" size="sm" className="flex-1">
                Approve & Continue
              </Button>
            </motion.div>
          </motion.div>
        </div>
      ),
    },
    // Phase 6: Design Agent
    {
      id: 5,
      phase: "Code Generation",
      title: "Create Execution Plan",
      description: "The Design Agent explores the codebase and creates a detailed plan.json with exact code changes, contracts, and execution order.",
      icon: <Workflow size={24} />,
      agent: "Design Agent",
      visual: (
        <div className="relative h-56 flex items-center justify-center p-4">
          <div className="flex items-center gap-6">
            {/* Code exploration */}
            <motion.div
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              className="flex flex-col gap-2"
            >
              {["read_file()", "grep()", "list_directory()", "query_graph()"].map((tool, i) => (
                <motion.div
                  key={tool}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.2 + i * 0.1 }}
                  className="px-2 py-1 rounded bg-[var(--color-bg-elevated)] border border-[var(--color-glass-border)] text-[10px] font-mono text-[var(--color-text-muted)]"
                >
                  {tool}
                </motion.div>
              ))}
            </motion.div>

            {/* Arrow */}
            <motion.div
              initial={{ opacity: 0, scale: 0 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: 0.6 }}
            >
              <ChevronRight size={24} className="text-[var(--color-accent)]" />
            </motion.div>

            {/* Plan output */}
            <motion.div
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.7 }}
              className="bg-[var(--color-bg-elevated)] rounded-lg border border-[var(--color-accent)]/30 p-3 w-48"
            >
              <div className="text-xs font-medium text-[var(--color-accent)] mb-2">plan.json</div>
              <div className="space-y-1 text-[10px] font-mono text-[var(--color-text-muted)]">
                <div>{"{"}</div>
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.9 }}
                  className="pl-2"
                >
                  tasks: [5],
                </motion.div>
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 1.0 }}
                  className="pl-2"
                >
                  contracts: [2],
                </motion.div>
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 1.1 }}
                  className="pl-2"
                >
                  phases: [3]
                </motion.div>
                <div>{"}"}</div>
              </div>
            </motion.div>
          </div>
        </div>
      ),
    },
    // Phase 7: Coordinator
    {
      id: 6,
      phase: "Code Generation",
      title: "Validate Plan",
      description: "The Coordinator Agent validates that all files exist, no circular dependencies, and contracts are valid before execution.",
      icon: <CheckCircle2 size={24} />,
      agent: "Coordinator Agent",
      visual: (
        <div className="relative h-56 flex items-center justify-center p-4">
          <div className="grid grid-cols-2 gap-4 w-full max-w-sm">
            {[
              { label: "Files exist", icon: FileCode2, status: "pass" },
              { label: "No circular deps", icon: GitBranch, status: "pass" },
              { label: "Contracts valid", icon: FileCheck, status: "pass" },
              { label: "Phases safe", icon: Workflow, status: "pass" },
            ].map((check, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 0.2 + i * 0.15 }}
                className="flex items-center gap-2 p-3 rounded-lg bg-[var(--color-bg-elevated)] border border-[var(--color-glass-border)]"
              >
                <check.icon size={16} className="text-[var(--color-text-muted)]" />
                <span className="text-xs text-[var(--color-text-secondary)] flex-1">{check.label}</span>
                <motion.div
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{ delay: 0.5 + i * 0.15, type: "spring" }}
                >
                  <CheckCircle2 size={14} className="text-[var(--color-success)]" />
                </motion.div>
              </motion.div>
            ))}
          </div>
        </div>
      ),
    },
    // Phase 8: Implementation
    {
      id: 7,
      phase: "Code Generation",
      title: "Generate Code",
      description: "Implementation Agents execute tasks in parallel (by phase), generating unified diffs for each file change.",
      icon: <Code2 size={24} />,
      agent: "Implementation Agent(s)",
      visual: (
        <div className="relative h-56 flex items-center justify-center p-4">
          <div className="space-y-3 w-full max-w-md">
            {[
              { file: "clients/httpClient.js", action: "CREATE", progress: 100 },
              { file: "clients/paymentClient.js", action: "MODIFY", progress: 100 },
              { file: "clients/accountClient.js", action: "MODIFY", progress: 75 },
            ].map((task, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.2 + i * 0.2 }}
                className="flex items-center gap-3 p-3 rounded-lg bg-[var(--color-bg-elevated)] border border-[var(--color-glass-border)]"
              >
                <Code2 size={16} className="text-[var(--color-accent)]" />
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-mono text-[var(--color-text-primary)] truncate">{task.file}</div>
                  <div className="flex items-center gap-2 mt-1">
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded ${
                        task.action === "CREATE"
                          ? "bg-[var(--color-success-subtle)] text-[var(--color-success)]"
                          : "bg-[var(--color-warning-subtle)] text-[var(--color-warning)]"
                      }`}
                    >
                      {task.action}
                    </span>
                    <div className="flex-1 h-1 bg-[var(--color-bg-base)] rounded-full overflow-hidden">
                      <motion.div
                        initial={{ width: 0 }}
                        animate={{ width: `${task.progress}%` }}
                        transition={{ delay: 0.5 + i * 0.2, duration: 0.5 }}
                        className="h-full bg-[var(--color-accent)]"
                      />
                    </div>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      ),
    },
    // Phase 9: Verifier
    {
      id: 8,
      phase: "Code Generation",
      title: "Verify Diffs",
      description: "The Verifier Agent checks that generated diffs exactly match the plan — correct files, contract signatures, and all specified changes.",
      icon: <FileCheck size={24} />,
      agent: "Verifier Agent",
      visual: (
        <div className="relative h-56 flex items-center justify-center p-4">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="w-full max-w-sm bg-[var(--color-bg-elevated)] rounded-xl border border-[var(--color-success)]/30 p-4"
          >
            <div className="flex items-center gap-2 mb-4">
              <FileCheck size={20} className="text-[var(--color-success)]" />
              <span className="text-sm font-medium text-[var(--color-text-primary)]">Verification Passed</span>
            </div>
            <div className="space-y-2">
              {[
                "Task compliance: 5/5 ✓",
                "Contract signatures: match ✓",
                "No extra changes ✓",
                "Syntax valid ✓",
              ].map((item, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.3 + i * 0.1 }}
                  className="text-xs text-[var(--color-text-secondary)] font-mono"
                >
                  {item}
                </motion.div>
              ))}
            </div>
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.8 }}
              className="mt-4 p-2 rounded bg-[var(--color-success-subtle)] text-center"
            >
              <span className="text-xs font-medium text-[var(--color-success)]">Ready for approval</span>
            </motion.div>
          </motion.div>
        </div>
      ),
    },
    // Phase 10: Final Approval
    {
      id: 9,
      phase: "Approval Gate",
      title: "Review & Apply Diffs",
      description: "You review the generated code diffs side-by-side. Approve to apply changes to your codebase, or request refinements.",
      icon: <GitPullRequest size={24} />,
      visual: (
        <div className="relative h-56 flex items-center justify-center p-4">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="w-full max-w-md bg-[var(--color-bg-elevated)] rounded-xl border border-[var(--color-glass-border)] overflow-hidden"
          >
            <div className="p-2 border-b border-[var(--color-glass-border)] flex items-center gap-2">
              <span className="text-xs font-mono text-[var(--color-text-muted)]">clients/httpClient.js</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-success-subtle)] text-[var(--color-success)]">
                +45 lines
              </span>
            </div>
            <div className="p-3 font-mono text-[10px] leading-relaxed bg-[var(--color-bg-base)]">
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.3 }}
                className="text-[var(--color-success)]"
              >
                + async function retry(fn, maxAttempts, delay) {"{"}
              </motion.div>
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.4 }}
                className="text-[var(--color-success)] pl-4"
              >
                + for (let i = 0; i {"<"} maxAttempts; i++) {"{"}
              </motion.div>
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.5 }}
                className="text-[var(--color-success)] pl-8"
              >
                + try {"{"} return await fn(); {"}"}
              </motion.div>
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.6 }}
                className="text-[var(--color-text-muted)] pl-8"
              >
                ...
              </motion.div>
            </div>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.8 }}
              className="p-3 border-t border-[var(--color-glass-border)] flex gap-2"
            >
              <Button variant="ghost" size="sm" className="flex-1">
                Request Changes
              </Button>
              <Button variant="primary" size="sm" className="flex-1">
                <CheckCircle2 size={14} />
                Apply to Codebase
              </Button>
            </motion.div>
          </motion.div>
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
    }, 4000);

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

  // Group steps by phase for the phase indicator
  const phases = [
    { name: "Start", steps: [0] },
    { name: "Impact Analysis", steps: [1, 2, 3] },
    { name: "Approval", steps: [4] },
    { name: "Code Generation", steps: [5, 6, 7, 8] },
    { name: "Final", steps: [9] },
  ];

  const currentPhaseIndex = phases.findIndex((p) => p.steps.includes(currentStep));

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
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-[var(--color-accent)] to-[var(--color-accent-hover)] flex items-center justify-center">
                <Sparkles size={20} className="text-white" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">
                  How Forge Works
                </h2>
                <p className="text-sm text-[var(--color-text-muted)]">
                  End-to-end AI code generation
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

          {/* Phase Progress */}
          <div className="px-6 pt-4">
            <div className="flex items-center gap-1">
              {phases.map((phase, i) => (
                <div key={i} className="flex items-center">
                  <button
                    onClick={() => setCurrentStep(phase.steps[0])}
                    className={`px-3 py-1 rounded-full text-xs font-medium transition-all ${
                      i === currentPhaseIndex
                        ? "bg-[var(--color-accent)] text-white"
                        : i < currentPhaseIndex
                        ? "bg-[var(--color-accent-subtle)] text-[var(--color-accent)]"
                        : "bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)]"
                    }`}
                  >
                    {phase.name}
                  </button>
                  {i < phases.length - 1 && (
                    <ChevronRight size={14} className="text-[var(--color-text-muted)] mx-1" />
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Step Progress */}
          <div className="px-6 pt-3">
            <div className="flex items-center gap-1">
              {steps.map((s, i) => (
                <button
                  key={s.id}
                  onClick={() => setCurrentStep(i)}
                  className={`flex-1 h-1 rounded-full transition-all ${
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
                <div className="flex items-start gap-4 mb-4">
                  <div className="w-12 h-12 rounded-xl bg-[var(--color-accent-subtle)] flex items-center justify-center text-[var(--color-accent)] flex-shrink-0">
                    {step.icon}
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="text-xl font-semibold text-[var(--color-text-primary)]">
                        {step.title}
                      </h3>
                      {step.agent && (
                        <button
                          onClick={() => setSelectedAgent(AGENT_DETAILS[step.agent!])}
                          className="px-2 py-0.5 rounded-full bg-[var(--color-accent-subtle)] text-[10px] font-medium text-[var(--color-accent)] hover:bg-[var(--color-accent)] hover:text-white transition-colors cursor-pointer flex items-center gap-1"
                        >
                          <Bot size={10} />
                          {step.agent}
                        </button>
                      )}
                    </div>
                    <p className="text-sm text-[var(--color-text-secondary)]">
                      {step.description}
                    </p>
                  </div>
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

            <div className="flex items-center gap-2 text-xs text-[var(--color-text-muted)]">
              <Bot size={14} />
              <span>6 specialized agents</span>
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
              {currentStep === steps.length - 1 ? "Get Started" : "Next"}
              {currentStep < steps.length - 1 && <ChevronRight size={16} />}
            </Button>
          </div>
        </motion.div>

        {/* Agent Detail Modal */}
        <AnimatePresence>
          {selectedAgent && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 z-60 flex items-center justify-center p-4"
              onClick={() => setSelectedAgent(null)}
            >
              <div className="absolute inset-0 bg-black/40" />
              <motion.div
                initial={{ opacity: 0, scale: 0.95, y: 20 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 20 }}
                onClick={(e) => e.stopPropagation()}
                className="relative w-full max-w-lg bg-[var(--color-bg-surface)] border border-[var(--color-glass-border)] rounded-2xl shadow-2xl overflow-hidden max-h-[80vh] flex flex-col"
              >
                {/* Agent Header */}
                <div className="p-4 border-b border-[var(--color-glass-border)] flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-[var(--color-accent)] flex items-center justify-center">
                      <Bot size={20} className="text-white" />
                    </div>
                    <div>
                      <h3 className="text-lg font-semibold text-[var(--color-text-primary)]">
                        {selectedAgent.name}
                      </h3>
                      <p className="text-xs text-[var(--color-accent)]">{selectedAgent.role}</p>
                    </div>
                  </div>
                  <button
                    onClick={() => setSelectedAgent(null)}
                    className="p-2 rounded-lg hover:bg-[var(--color-bg-elevated)] transition-colors"
                  >
                    <X size={18} className="text-[var(--color-text-muted)]" />
                  </button>
                </div>

                {/* Agent Content */}
                <div className="flex-1 overflow-auto p-4 space-y-4">
                  {/* Goal */}
                  <div>
                    <div className="flex items-center gap-2 mb-2">
                      <Target size={14} className="text-[var(--color-accent)]" />
                      <span className="text-xs font-semibold text-[var(--color-text-primary)] uppercase tracking-wide">Goal</span>
                    </div>
                    <p className="text-sm text-[var(--color-text-secondary)] leading-relaxed">
                      {selectedAgent.goal}
                    </p>
                  </div>

                  {/* How It Works */}
                  <div>
                    <div className="flex items-center gap-2 mb-2">
                      <Zap size={14} className="text-[var(--color-warning)]" />
                      <span className="text-xs font-semibold text-[var(--color-text-primary)] uppercase tracking-wide">How It Works</span>
                    </div>
                    <div className="space-y-1.5">
                      {selectedAgent.howItWorks.map((step, i) => (
                        <div key={i} className="flex items-start gap-2">
                          <span className="w-5 h-5 rounded-full bg-[var(--color-bg-elevated)] flex items-center justify-center text-[10px] font-medium text-[var(--color-text-muted)] flex-shrink-0 mt-0.5">
                            {i + 1}
                          </span>
                          <span className="text-sm text-[var(--color-text-secondary)]">{step}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Tools */}
                  {selectedAgent.tools.length > 0 && (
                    <div>
                      <div className="flex items-center gap-2 mb-2">
                        <Wrench size={14} className="text-[var(--color-success)]" />
                        <span className="text-xs font-semibold text-[var(--color-text-primary)] uppercase tracking-wide">Tools Available</span>
                      </div>
                      <div className="space-y-2">
                        {selectedAgent.tools.map((tool, i) => (
                          <div key={i} className="p-2 rounded-lg bg-[var(--color-bg-base)] border border-[var(--color-glass-border)]">
                            <code className="text-xs font-mono text-[var(--color-accent)]">{tool.name}</code>
                            <p className="text-xs text-[var(--color-text-muted)] mt-0.5">{tool.description}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Input/Output */}
                  <div className="grid grid-cols-2 gap-3">
                    <div className="p-3 rounded-lg bg-[var(--color-bg-base)] border border-[var(--color-glass-border)]">
                      <div className="flex items-center gap-1.5 mb-1">
                        <ChevronRight size={12} className="text-[var(--color-text-muted)]" />
                        <span className="text-[10px] font-semibold text-[var(--color-text-muted)] uppercase">Input</span>
                      </div>
                      <p className="text-xs text-[var(--color-text-secondary)]">{selectedAgent.input}</p>
                    </div>
                    <div className="p-3 rounded-lg bg-[var(--color-bg-base)] border border-[var(--color-glass-border)]">
                      <div className="flex items-center gap-1.5 mb-1">
                        <ChevronLeft size={12} className="text-[var(--color-text-muted)]" />
                        <span className="text-[10px] font-semibold text-[var(--color-text-muted)] uppercase">Output</span>
                      </div>
                      <p className="text-xs text-[var(--color-text-secondary)]">{selectedAgent.output}</p>
                    </div>
                  </div>
                </div>

                {/* Footer */}
                <div className="p-4 border-t border-[var(--color-glass-border)]">
                  <Button
                    variant="secondary"
                    size="sm"
                    className="w-full"
                    onClick={() => setSelectedAgent(null)}
                  >
                    Close
                  </Button>
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </AnimatePresence>
  );
}
