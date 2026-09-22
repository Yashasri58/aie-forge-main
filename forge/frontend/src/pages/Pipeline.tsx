import { useEffect, useState, useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  CheckCircle2,
  RefreshCw,
  AlertCircle,
  Zap,
} from "lucide-react";
import { Page, Header, Card, Progress, Badge } from "../components/ui";
import { getPipelineStatus } from "../api";
import type { PipelineState } from "../types";

interface LogEntry {
  time: string;
  message: string;
  type: "info" | "success" | "warning" | "error";
}

const STAGE_CONFIG: Record<string, { icon: React.ReactNode; label: string; message: string }> = {
  requirements_ready: {
    icon: <Search size={32} />,
    label: "Starting Analysis",
    message: "Preparing to analyze your requirements...",
  },
  analyzing: {
    icon: <Search size={32} />,
    label: "Analyzing Impact",
    message: "Tracing call paths and dependencies...",
  },
  verifying: {
    icon: <CheckCircle2 size={32} />,
    label: "Verifying Results",
    message: "Checking completeness of analysis...",
  },
  filling_gaps: {
    icon: <RefreshCw size={32} />,
    label: "Filling Gaps",
    message: "Expanding analysis to cover missing paths...",
  },
};

export default function Pipeline() {
  const { pipelineId } = useParams();
  const navigate = useNavigate();
  
  const [pipeline, setPipeline] = useState<PipelineState | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const esRef = useRef<EventSource | null>(null);
  const logsEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!pipelineId) return;

    // Fetch initial state immediately
    fetchAndUpdate(pipelineId);

    // Open SSE stream
    const es = new EventSource(`/pipeline/${pipelineId}/stream`);
    esRef.current = es;

    es.onmessage = () => { fetchAndUpdate(pipelineId); };
    es.addEventListener("stage", () => { fetchAndUpdate(pipelineId); });
    es.addEventListener("done", () => { es.close(); fetchAndUpdate(pipelineId); });
    es.onerror = () => { es.close(); };

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [pipelineId]);

  // Auto-scroll logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  // Navigate when complete
  useEffect(() => {
    if (pipeline?.stage === "awaiting_approval") {
      navigate(`/results/${pipeline.id}`);
    } else if (pipeline?.stage === "failed") {
      // Show error, could navigate back
      addLog("Pipeline failed: " + (pipeline.error || "Unknown error"), "error");
    }
  }, [pipeline?.stage, pipeline?.id, pipeline?.error, navigate]);

  async function fetchAndUpdate(id: string): Promise<PipelineState | null> {
    try {
      const state = await getPipelineStatus(id);
      
      // Use activity_log from backend if available
      if (state.activity_log && state.activity_log.length > 0) {
        // Convert backend activity log to our format
        const backendLogs = state.activity_log.map((entry: { time: number; message: string; level: string }) => ({
          time: new Date(entry.time * 1000).toLocaleTimeString("en-US", {
            hour12: false,
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          }),
          message: entry.message,
          type: entry.level as LogEntry["type"],
        }));
        
        // Only update if we have new logs
        if (backendLogs.length > logs.length) {
          setLogs(backendLogs);
        }
      } else {
        // Fallback: Generate log entries based on state changes
        if (!pipeline || pipeline.stage !== state.stage) {
          addLog(`Stage: ${state.stage}`, "info");
        }
      }
      
      setPipeline(state);
      return state;
    } catch (err) {
      console.error("Failed to poll pipeline:", err);
      addLog("Failed to fetch pipeline status", "error");
      return null;
    }
  }

  function addLog(message: string, type: LogEntry["type"] = "info") {
    const time = new Date().toLocaleTimeString("en-US", {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
    setLogs((prev) => [...prev, { time, message, type }]);
  }

  const stageConfig = STAGE_CONFIG[pipeline?.stage || "requirements_ready"] || STAGE_CONFIG.requirements_ready;
  const iteration = pipeline?.iteration || 1;
  const maxIterations = pipeline?.max_iterations || 3;
  const progressPercent = pipeline?.stage === "requirements_ready" ? 5
    : pipeline?.stage === "analyzing" ? 33 
    : pipeline?.stage === "verifying" ? 66 
    : pipeline?.stage === "filling_gaps" ? 80 + (iteration / maxIterations) * 20
    : 10;

  return (
    <Page className="flex flex-col">
      <Header
        step={{ current: 3, total: 4, label: "Processing" }}
      />

      <div className="flex-1 flex flex-col items-center justify-center max-w-3xl mx-auto w-full py-8">
        {/* Animated Icon */}
        <motion.div
          className="relative mb-8"
          initial={{ scale: 0.8, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
        >
          {/* Outer glow rings */}
          <motion.div
            className="absolute inset-0 rounded-full bg-[var(--color-accent)]"
            animate={{
              scale: [1, 1.5, 1],
              opacity: [0.3, 0, 0.3],
            }}
            transition={{
              duration: 2,
              repeat: Infinity,
              ease: "easeInOut",
            }}
            style={{ width: 120, height: 120, margin: -20 }}
          />
          <motion.div
            className="absolute inset-0 rounded-full bg-[var(--color-accent)]"
            animate={{
              scale: [1, 1.3, 1],
              opacity: [0.2, 0, 0.2],
            }}
            transition={{
              duration: 2,
              repeat: Infinity,
              ease: "easeInOut",
              delay: 0.3,
            }}
            style={{ width: 120, height: 120, margin: -20 }}
          />
          
          {/* Main icon container */}
          <div className="w-20 h-20 rounded-2xl bg-[var(--color-accent-subtle)] border border-[var(--color-accent)] flex items-center justify-center text-[var(--color-accent)]">
            <motion.div
              animate={pipeline?.stage === "filling_gaps" ? { rotate: 360 } : {}}
              transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
            >
              {stageConfig.icon}
            </motion.div>
          </div>
        </motion.div>

        {/* Stage Label */}
        <motion.h1
          className="text-2xl font-semibold text-[var(--color-text-primary)] mb-2"
          key={pipeline?.stage}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
        >
          {stageConfig.label}
        </motion.h1>

        <motion.p
          className="text-[var(--color-text-secondary)] mb-8"
          key={`${pipeline?.stage}-msg`}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
        >
          {stageConfig.message}
        </motion.p>

        {/* Progress Bar */}
        <div className="w-full max-w-md mb-8">
          <Progress value={progressPercent} />
          <div className="flex justify-between mt-3 text-xs text-[var(--color-text-muted)]">
            <span className={pipeline?.stage === "analyzing" ? "text-[var(--color-accent)]" : ""}>
              Analyze
            </span>
            <span className={pipeline?.stage === "verifying" ? "text-[var(--color-accent)]" : ""}>
              Verify
            </span>
            <span className={pipeline?.stage === "filling_gaps" ? "text-[var(--color-accent)]" : ""}>
              Complete
            </span>
          </div>
        </div>

        {/* Iteration Badge */}
        <AnimatePresence>
          {iteration > 1 && (
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9 }}
            >
              <Badge variant="warning" className="mb-8">
                <RefreshCw size={12} />
                Iteration {iteration} of {maxIterations}
              </Badge>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Live Log Terminal */}
        <Card className="w-full terminal">
          <div className="terminal-header">
            <span className="terminal-dot terminal-dot-red" />
            <span className="terminal-dot terminal-dot-yellow" />
            <span className="terminal-dot terminal-dot-green" />
            <span className="ml-auto text-xs text-[var(--color-text-muted)] flex items-center gap-2">
              <Zap size={12} className="text-[var(--color-success)]" />
              Live
            </span>
          </div>
          <div className="terminal-body max-h-48 overflow-y-auto">
            <AnimatePresence>
              {logs.map((log, i) => (
                <motion.div
                  key={i}
                  className="terminal-line"
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                >
                  <span className="terminal-time">{log.time}</span>
                  <span
                    className={
                      log.type === "success"
                        ? "text-[var(--color-success)]"
                        : log.type === "error"
                        ? "text-[var(--color-error)]"
                        : log.type === "warning"
                        ? "text-[var(--color-warning)]"
                        : "terminal-message"
                    }
                  >
                    {log.type === "success" && <CheckCircle2 size={12} className="inline mr-2" />}
                    {log.type === "error" && <AlertCircle size={12} className="inline mr-2" />}
                    {log.message}
                  </span>
                </motion.div>
              ))}
            </AnimatePresence>
            
            {/* Blinking cursor */}
            <div className="terminal-line">
              <span className="terminal-time opacity-0">00:00:00</span>
              <span className="cursor-blink" />
            </div>
            <div ref={logsEndRef} />
          </div>
        </Card>
      </div>
    </Page>
  );
}
