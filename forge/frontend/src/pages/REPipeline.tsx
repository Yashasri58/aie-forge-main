/**
 * REPipeline — Live progress page for the Reverse Engineer pipeline.
 *
 * Polls GET /reverse-engineer/:id every 1 second.
 * Shows 6-stage progress bar + live activity log.
 * Auto-navigates to /reverse-engineer/:id/spec when stage=complete.
 *
 * Key fix: navigate() is called from useEffect watching session.stage,
 * NOT from inside the poll callback — this ensures React renders the
 * session data (logs, stage bar) before the redirect fires.
 */

import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { getREStatus } from "../api";
import type { ReverseEngineerSession, REStage, REActivity } from "../types";

// ─── Stage metadata ──────────────────────────────────────────────────────────

const STAGES: { id: REStage; label: string; icon: string; desc: string }[] = [
  { id: "uploading",  label: "Uploading",  icon: "📤", desc: "File received" },
  { id: "parsing",    label: "Parsing",    icon: "🔬", desc: "Deterministic log parsing" },
  { id: "extracting", label: "Templates",  icon: "🗂️", desc: "Drain3 template mining" },
  { id: "inferring",  label: "Inferring",  icon: "🧠", desc: "Gemini 3.1 Pro inference" },
  { id: "gap_review", label: "Gap Review", icon: "🔍", desc: "Gemini 3.5 Flash review" },
  { id: "writing",    label: "Writing",    icon: "📝", desc: "Generating spec sections" },
  { id: "complete",   label: "Complete",   icon: "✅", desc: "Spec ready" },
];

const STAGE_ORDER = STAGES.map((s) => s.id);

function stageIndex(stage: REStage): number {
  return STAGE_ORDER.indexOf(stage);
}

// ─── Activity log entry ───────────────────────────────────────────────────────

function ActivityEntry({ entry }: { entry: REActivity }) {
  const levelColors: Record<string, string> = {
    info: "text-gray-300",
    warning: "text-amber-400",
    error: "text-red-400",
  };

  const ts = new Date(entry.time * 1000).toLocaleTimeString("en", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  return (
    <motion.div
      initial={{ opacity: 0, x: -6 }}
      animate={{ opacity: 1, x: 0 }}
      className={`flex gap-3 text-sm font-mono ${levelColors[entry.level] ?? "text-gray-300"}`}
    >
      <span className="text-gray-600 shrink-0">{ts}</span>
      <span>{entry.message}</span>
    </motion.div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function REPipeline() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [session, setSession] = useState<ReverseEngineerSession | null>(null);
  const [error, setError] = useState<string | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const mountedAtRef = useRef<number>(Date.now());
  const redirectedRef = useRef(false);

  // ── Poll backend for session state ─────────────────────────────────────────
  const slowedRef = useRef(false); // track whether we've already switched to slow interval

  const poll = async () => {
    if (!id) return;
    try {
      const s = await getREStatus(id);
      setSession(s);

      if (s.stage === "failed") {
        clearInterval(pollRef.current!);
        pollRef.current = null;
        setError(s.error ?? "Pipeline failed");
        return;
      }

      if (s.stage === "complete") {
        // Stop polling — redirect useEffect handles navigation
        clearInterval(pollRef.current!);
        pollRef.current = null;
        return;
      }

      // Once past fast initial stages, switch ONCE to 1500ms to reduce server load
      const fastStages = ["uploading", "parsing", "extracting"];
      if (!slowedRef.current && !fastStages.includes(s.stage)) {
        slowedRef.current = true;
        clearInterval(pollRef.current!);
        pollRef.current = setInterval(poll, 1500);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load status");
      clearInterval(pollRef.current!);
      pollRef.current = null;
    }
  };

  useEffect(() => {
    slowedRef.current = false;
    poll();
    // Start fast (200ms) to catch stage 1+2 which complete in <100ms
    pollRef.current = setInterval(poll, 200);
    return () => {
      clearInterval(pollRef.current!);
      pollRef.current = null;
    };
  }, [id]);

  // ── Redirect AFTER React has rendered the completed session ────────────────
  useEffect(() => {
    if (session?.stage === "complete" && !redirectedRef.current) {
      redirectedRef.current = true;
      // poll() already cleared the interval — just navigate after brief delay
      const elapsed = Date.now() - mountedAtRef.current;
      const delay = Math.max(2000 - elapsed, 800);
      setTimeout(() => navigate(`/reverse-engineer/${id}/spec`), delay);
    }
  }, [session?.stage]);

  // ── Auto-scroll activity log ────────────────────────────────────────────────
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [session?.activity_log?.length]);

  // ── Loading state (first poll not yet returned) — show stage UI immediately ──
  // Don't show a blank loading screen; render the full pipeline layout right away.
  // session will be null briefly until the first poll returns (~1s).
  const currentIdx = session ? stageIndex(session.stage) : 0;

  return (
    <div className="min-h-screen bg-[#0d1117] text-gray-100 flex flex-col">
      {/* Header */}
      <header className="flex items-center gap-3 px-6 py-4 border-b border-white/10">
        <button
          onClick={() => navigate("/")}
          className="text-gray-400 hover:text-white transition-colors text-sm"
        >
          ← Dashboard
        </button>
        <span className="text-gray-600">/</span>
        <span className="text-gray-300 font-medium">Reverse Engineer</span>
        <span className="text-gray-600">/</span>
        <span className="text-gray-400 font-mono text-xs">{id?.slice(0, 8)}…</span>
      </header>

      <main className="flex-1 flex flex-col gap-6 p-6 max-w-4xl mx-auto w-full">
        {/* File info */}
        {session && (
          <div className="rounded-xl border border-white/10 bg-white/5 px-5 py-4 flex items-center gap-4">
            <span className="text-2xl">📄</span>
            <div>
              <p className="font-semibold text-white">{session.log_file_name}</p>
              {session.user_comments && (
                <p className="text-sm text-gray-400 mt-0.5 line-clamp-1">
                  Context: {session.user_comments}
                </p>
              )}
            </div>
          </div>
        )}

        {/* Stage progress */}
        <div className="rounded-xl border border-white/10 bg-white/5 p-5 space-y-4">
          <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
            Pipeline Progress
          </h2>

          <div className="flex items-start gap-0">
            {STAGES.map((stage, i) => {
              const done = i < currentIdx;
              const active = i === currentIdx;
              const failed = session?.stage === "failed" && active;

              return (
                <div key={stage.id} className="flex-1 flex flex-col items-center">
                  {/* Connector line */}
                  <div className="w-full flex items-center">
                    <div className={`h-0.5 flex-1 ${i === 0 ? "invisible" : done || active ? "bg-blue-500" : "bg-white/10"}`} />
                    <div
                      className={`
                        w-8 h-8 rounded-full flex items-center justify-center text-sm shrink-0
                        ${failed
                          ? "bg-red-600"
                          : active
                          ? "bg-blue-600 ring-4 ring-blue-600/30"
                          : done
                          ? "bg-emerald-600"
                          : "bg-white/10 text-gray-500"
                        }
                      `}
                    >
                      {failed ? "✗" : done ? "✓" : active ? (
                        <span className="h-3 w-3 rounded-full border-2 border-white/30 border-t-white animate-spin" />
                      ) : (
                        <span className="text-xs text-gray-500">{i + 1}</span>
                      )}
                    </div>
                    <div className={`h-0.5 flex-1 ${i === STAGES.length - 1 ? "invisible" : done ? "bg-blue-500" : "bg-white/10"}`} />
                  </div>
                  {/* Label */}
                  <div className={`mt-2 text-center ${active ? "text-white" : done ? "text-emerald-400" : "text-gray-600"}`}>
                    <div className="text-xs font-medium">{stage.label}</div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Current detail */}
          {session?.current_stage_detail && (
            <p className="text-sm text-gray-400 text-center">
              {session.current_stage_detail}
            </p>
          )}
        </div>

        {/* Stats (available after parsing) */}
        {session?.extracted_facts && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="grid grid-cols-3 gap-3"
          >
            {[
              { label: "Services", value: session.extracted_facts.service_count ?? session.service_count },
              { label: "Endpoints", value: session.extracted_facts.endpoint_count ?? 0 },
              { label: "Traces", value: session.extracted_facts.trace_count ?? 0 },
            ].map((s) => (
              <div
                key={s.label}
                className="rounded-xl border border-white/10 bg-white/5 p-4 text-center"
              >
                <div className="text-2xl font-bold text-white">{s.value}</div>
                <div className="text-xs text-gray-400 mt-1">{s.label}</div>
              </div>
            ))}
          </motion.div>
        )}

        {/* Error */}
        {(error || session?.stage === "failed") && (
          <div className="rounded-xl bg-red-950/50 border border-red-500/30 px-5 py-4 space-y-2">
            <p className="font-semibold text-red-300">Pipeline Failed</p>
            <p className="text-sm text-red-400">{error ?? session?.error}</p>
            <button
              onClick={() => navigate("/")}
              className="mt-2 text-sm text-red-400 hover:text-red-200 underline"
            >
              Back to Dashboard
            </button>
          </div>
        )}

        {/* Activity log */}
        {session && session.activity_log.length > 0 && (
          <div className="rounded-xl border border-white/10 bg-black/40 p-5 space-y-2 max-h-96 overflow-y-auto font-mono">
            <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider sticky top-0 bg-black/40 pb-1">
              Activity Log
            </h2>
            <AnimatePresence initial={false}>
              {session.activity_log.map((entry, i) => (
                <ActivityEntry key={i} entry={entry} />
              ))}
            </AnimatePresence>
            <div ref={logEndRef} />
          </div>
        )}

        {/* Complete notice */}
        {session?.stage === "complete" && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="rounded-xl border border-emerald-500/30 bg-emerald-950/30 p-5 text-center space-y-3"
          >
            <div className="text-3xl">✅</div>
            <p className="font-semibold text-emerald-300">
              Spec complete — {session.spec_section_count} sections generated
            </p>
            <p className="text-sm text-gray-400">Redirecting to spec viewer…</p>
          </motion.div>
        )}
      </main>
    </div>
  );
}
