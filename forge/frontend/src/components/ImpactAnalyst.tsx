import { useCallback, useEffect, useRef, useState } from "react";
import {
  startPipeline,
  respondToPipeline,
  confirmRequirements,
  approvePipeline,
  deletePipeline,
  getGraphStats,
} from "../api";
import type { PipelineState, GraphStats } from "../types";

// ─── FUNNY LOADING MESSAGES ───────────────────────────────────────────────────

const GATHERING_MESSAGES = [
  "🤔 Pondering your requirements...",
  "📋 Taking notes furiously...",
  "🧐 Reading between the lines...",
];

const ANALYZING_MESSAGES = [
  "🔍 Searching through spaghetti code...",
  "🕵️ Following the dependency rabbit hole...",
  "🎯 Finding all the things that could break...",
  "📊 Consulting the sacred dependency graph...",
  "🧬 Analyzing the DNA of your codebase...",
  "🔬 Putting functions under the microscope...",
  "🌐 Mapping the interconnected web of chaos...",
];

const SCORING_MESSAGES = [
  "⚖️ Weighing the risks like a paranoid architect...",
  "🎲 Rolling dice for risk scores... just kidding, using math!",
  "💀 Identifying the 'touch this and everything dies' zones...",
  "🚨 Calibrating the 'oh no' meter...",
  "📈 Calculating blast radius (hopefully small)...",
];

const PLANNING_MESSAGES = [
  "📝 Writing tasks that future-you will thank us for...",
  "🧩 Arranging the puzzle pieces into a plan...",
  "🗺️ Drawing the treasure map to completion...",
  "⏱️ Estimating effort (adding 2x buffer for reality)...",
  "🎬 Directing the implementation screenplay...",
];

const CHAIN_MESSAGES = [
  "🔗 Checking for domino effects...",
  "🌊 Tracing the ripples through the system...",
  "🤯 Wait, that change affects WHAT?!",
  "🔄 Going deeper down the rabbit hole...",
];

const VERIFYING_MESSAGES = [
  "✅ Double-checking our homework...",
  "🔍 Verifying all call paths are traced...",
  "🧪 Testing the impact analysis for completeness...",
  "📋 Making sure we didn't miss anything...",
  "🔄 Running verification loop...",
];

const FILLING_GAPS_MESSAGES = [
  "🔧 Filling in the missing pieces...",
  "📝 Adding the callers we missed...",
  "🕳️ Patching holes in the analysis...",
  "➕ Expanding the impact report...",
];

function getRandomMessage(messages: string[]): string {
  return messages[Math.floor(Math.random() * messages.length)];
}

function getMessageForStage(stage: string): string {
  switch (stage) {
    case "gathering":
      return getRandomMessage(GATHERING_MESSAGES);
    case "analyzing":
      return getRandomMessage(ANALYZING_MESSAGES);
    case "verifying":
      return getRandomMessage(VERIFYING_MESSAGES);
    case "filling_gaps":
      return getRandomMessage(FILLING_GAPS_MESSAGES);
    case "scoring":
      return getRandomMessage(SCORING_MESSAGES);
    case "planning":
      return getRandomMessage(PLANNING_MESSAGES);
    case "chain_analysis":
      return getRandomMessage(CHAIN_MESSAGES);
    default:
      return "🔄 Working on it...";
  }
}

// ─── MAIN COMPONENT ───────────────────────────────────────────────────────────

export default function ImpactAnalyst() {
  // Pipeline state
  const [pipeline, setPipeline] = useState<PipelineState | null>(null);
  const [waiting, setWaiting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<GraphStats | null>(null);

  // Input state
  const [title, setTitle] = useState("");
  const [requirements, setRequirements] = useState("");
  const [followUp, setFollowUp] = useState("");

  // Loading animation state
  const [loadingMessage, setLoadingMessage] = useState("");
  const [loadingDots, setLoadingDots] = useState("");

  const chatEndRef = useRef<HTMLDivElement>(null);

  // Load stats on mount
  useEffect(() => {
    getGraphStats().then(setStats).catch(() => null);
  }, []);

  // Auto-scroll chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [pipeline?.conversation_history, waiting]);

  // Rotate loading messages
  useEffect(() => {
    if (!pipeline || pipeline.stage === "gathering" || pipeline.stage === "awaiting_approval") {
      return;
    }

    setLoadingMessage(getMessageForStage(pipeline.stage));
    const interval = setInterval(() => {
      setLoadingMessage(getMessageForStage(pipeline.stage));
    }, 3000);

    return () => clearInterval(interval);
  }, [pipeline?.stage]);

  // Animate dots
  useEffect(() => {
    const interval = setInterval(() => {
      setLoadingDots((d) => (d.length >= 3 ? "" : d + "."));
    }, 400);
    return () => clearInterval(interval);
  }, []);

  // ── ACTIONS ──

  const handleSubmit = useCallback(async () => {
    if (!requirements.trim()) return;

    // Clear old pipeline
    if (pipeline?.id) {
      deletePipeline(pipeline.id).catch(() => null);
    }
    setPipeline(null);
    setError(null);
    setWaiting(true);

    const message = title.trim()
      ? `## ${title.trim()}\n\n${requirements.trim()}`
      : requirements.trim();

    try {
      const state = await startPipeline(message);
      setPipeline(state);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setWaiting(false);
    }
  }, [requirements, title, pipeline?.id]);

  const handleFollowUp = useCallback(async () => {
    if (!followUp.trim() || !pipeline?.id || waiting) return;

    const text = followUp.trim();
    setFollowUp("");
    setWaiting(true);

    try {
      const state = await respondToPipeline(pipeline.id, text);
      setPipeline(state);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setWaiting(false);
    }
  }, [followUp, pipeline?.id, waiting]);

  const handleApprove = useCallback(async () => {
    if (!pipeline?.id) return;
    setWaiting(true);
    try {
      const state = await approvePipeline(pipeline.id, true);
      setPipeline(state);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setWaiting(false);
    }
  }, [pipeline?.id]);

  const handleReject = useCallback(async () => {
    if (!pipeline?.id) return;
    setWaiting(true);
    try {
      const state = await approvePipeline(pipeline.id, false, "User rejected");
      setPipeline(state);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setWaiting(false);
    }
  }, [pipeline?.id]);

  const handleConfirmRequirements = useCallback(async () => {
    if (!pipeline?.id) return;
    setWaiting(true);
    try {
      const state = await confirmRequirements(pipeline.id);
      setPipeline(state);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setWaiting(false);
    }
  }, [pipeline?.id]);

  const handleNewSession = useCallback(() => {
    if (pipeline?.id) deletePipeline(pipeline.id).catch(() => null);
    setPipeline(null);
    setTitle("");
    setRequirements("");
    setFollowUp("");
    setError(null);
  }, [pipeline?.id]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleFollowUp();
    }
  };

  // ── RENDER LOGIC ──

  // Stage 1: No pipeline yet OR in gathering stage
  const isGathering = !pipeline || pipeline.stage === "gathering";
  
  // Stage 1.5: Requirements collected, awaiting user confirmation
  const isRequirementsReady = pipeline?.stage === "requirements_ready";
  
  // Stage 2: Pipeline is processing (analyzing, verifying, filling_gaps, etc.)
  const isProcessing = pipeline && ["analyzing", "verifying", "filling_gaps", "scoring", "planning", "chain_analysis"].includes(pipeline.stage);
  
  // Stage 3: Awaiting approval
  const isAwaitingApproval = pipeline?.stage === "awaiting_approval";
  
  // Final states
  const isComplete = pipeline?.stage === "approved" || pipeline?.stage === "rejected";

  return (
    <div className="analyst-shell">
      {/* ── LEFT PANEL: REQUIREMENTS INPUT ── */}
      <aside className="analyst-panel analyst-req-panel">
        <div className="analyst-panel-header">
          <span className="analyst-panel-title">New Analysis</span>
          <span className="analyst-panel-subtitle">
            Describe the change or requirement
          </span>
        </div>

        {stats && (
          <div className="analyst-stats-bar">
            <span><strong>{stats.services}</strong> services</span>
            <span><strong>{stats.symbols}</strong> symbols</span>
            <span><strong>{stats.edges}</strong> edges</span>
          </div>
        )}

        <div className="analyst-form">
          <label htmlFor="req-title">Change title (optional)</label>
          <input
            id="req-title"
            type="text"
            className="analyst-input"
            placeholder="e.g. Add 2FA to checkout flow"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            disabled={isProcessing || isAwaitingApproval}
          />

          <label htmlFor="req-text">Requirements / description</label>
          <textarea
            id="req-text"
            className="analyst-textarea"
            placeholder="Describe what you want to change or build. Be specific about which functions, services, or APIs are involved."
            value={requirements}
            onChange={(e) => setRequirements(e.target.value)}
            rows={10}
            disabled={isProcessing || isAwaitingApproval}
          />

          <button
            className="analyst-btn-primary"
            onClick={() => void handleSubmit()}
            disabled={waiting || !requirements.trim() || isProcessing || isAwaitingApproval}
          >
            {waiting && !pipeline ? "⏳ Starting..." : "🚀 Analyse Impact"}
          </button>

          {(pipeline || isComplete) && (
            <button className="analyst-btn-ghost" onClick={handleNewSession}>
              + New Analysis
            </button>
          )}
        </div>
      </aside>

      {/* ── MIDDLE: CONVERSATION OR LOADING OR RESULTS ── */}
      <main className="analyst-panel analyst-chat-panel">
        {/* GATHERING STAGE: Show conversation */}
        {isGathering && (
          <>
            <div className="analyst-panel-header" style={{ flexDirection: "row", alignItems: "center" }}>
              <span className="analyst-panel-title">💬 Conversation</span>
              {pipeline?.id && (
                <span className="analyst-session-badge">{pipeline.id.slice(0, 8)}…</span>
              )}
            </div>

            <div className="analyst-chat-messages">
              {(!pipeline || (pipeline.conversation_history?.length ?? 0) === 0) && !waiting && (
                <div className="analyst-empty-state">
                  <div className="analyst-empty-icon">💬</div>
                  <p>Submit requirements on the left to start a conversation with the Context Gatherer.</p>
                </div>
              )}

              {(pipeline?.conversation_history || []).map((msg, i) => (
                <ChatBubble key={i} role={msg.role} content={msg.content} />
              ))}

              {waiting && <TypingIndicator />}
              {error && <div className="analyst-error">⚠️ {error}</div>}

              <div ref={chatEndRef} />
            </div>

            <div className="analyst-chat-input-area">
              <textarea
                className="analyst-chat-input"
                placeholder="Respond to the agent's questions…"
                value={followUp}
                onChange={(e) => setFollowUp(e.target.value)}
                onKeyDown={handleKeyDown}
                rows={1}
                disabled={!pipeline || waiting}
              />
              <button
                className="analyst-send-btn"
                onClick={() => void handleFollowUp()}
                disabled={!followUp.trim() || !pipeline || waiting}
                title="Send"
              >
                ➤
              </button>
            </div>
          </>
        )}

        {/* REQUIREMENTS READY: Show summary and confirm button */}
        {isRequirementsReady && pipeline && (
          <div className="analyst-requirements-ready">
            <div className="analyst-panel-header">
              <span className="analyst-panel-title">✅ Requirements Collected</span>
            </div>
            
            <div className="analyst-requirements-summary">
              <h3>Collected Requirements</h3>
              
              <div className="analyst-req-card">
                <div className="analyst-req-label">Description</div>
                <div className="analyst-req-value">{pipeline.requirements?.description || "N/A"}</div>
              </div>
              
              {pipeline.requirements?.services && pipeline.requirements.services.length > 0 && (
                <div className="analyst-req-card">
                  <div className="analyst-req-label">Services</div>
                  <div className="analyst-req-value">
                    {pipeline.requirements.services.map((s: string, i: number) => (
                      <span key={i} className="analyst-tag">{s}</span>
                    ))}
                  </div>
                </div>
              )}
              
              {pipeline.requirements?.functions && pipeline.requirements.functions.length > 0 && (
                <div className="analyst-req-card">
                  <div className="analyst-req-label">Functions</div>
                  <div className="analyst-req-value">
                    {pipeline.requirements.functions.map((f: string, i: number) => (
                      <span key={i} className="analyst-tag analyst-tag-func">{f}</span>
                    ))}
                  </div>
                </div>
              )}
              
              {pipeline.requirements?.change_type && (
                <div className="analyst-req-card">
                  <div className="analyst-req-label">Change Type</div>
                  <div className="analyst-req-value">{pipeline.requirements.change_type}</div>
                </div>
              )}
              
              <div className="analyst-req-card">
                <div className="analyst-req-label">Clarity Score</div>
                <div className="analyst-req-value">
                  <span className="analyst-clarity-score">{pipeline.requirements?.clarity_score || 0}/10</span>
                </div>
              </div>
            </div>
            
            <div className="analyst-conversation-history">
              <h4>Conversation History</h4>
              {(pipeline.conversation_history || []).map((msg, i) => (
                <ChatBubble key={i} role={msg.role} content={msg.content} />
              ))}
            </div>
            
            <div className="analyst-confirm-actions">
              <p>Ready to analyze impact? This will run the Impact Analysis + Verification pipeline.</p>
              <div className="analyst-btn-row">
                <button
                  className="analyst-btn-primary analyst-btn-large"
                  onClick={() => void handleConfirmRequirements()}
                  disabled={waiting}
                >
                  {waiting ? "⏳ Starting Analysis..." : "✅ Confirm & Run Analysis"}
                </button>
                <button
                  className="analyst-btn-ghost"
                  onClick={handleNewSession}
                  disabled={waiting}
                >
                  ✏️ Edit Requirements
                </button>
              </div>
            </div>
          </div>
        )}

        {/* PROCESSING STAGE: Show funny loading screen */}
        {isProcessing && (
          <div className="analyst-loading-screen">
            <div className="analyst-loading-content">
              <div className="analyst-loading-spinner">
                <div className="analyst-spinner-ring"></div>
                <div className="analyst-spinner-icon">
                  {pipeline.stage === "analyzing" && "🔍"}
                  {pipeline.stage === "scoring" && "⚖️"}
                  {pipeline.stage === "planning" && "📝"}
                  {pipeline.stage === "chain_analysis" && "🔗"}
                </div>
              </div>
              
              <div className="analyst-loading-stage">
                {pipeline.current_agent || pipeline.stage}
              </div>
              
              <div className="analyst-loading-message">
                {loadingMessage}{loadingDots}
              </div>

              <div className="analyst-loading-progress">
                <div className="analyst-progress-bar">
                  <div 
                    className="analyst-progress-fill" 
                    style={{ 
                      width: pipeline.stage === "analyzing" ? "25%" :
                             pipeline.stage === "scoring" ? "50%" :
                             pipeline.stage === "planning" ? "75%" :
                             pipeline.stage === "chain_analysis" ? "90%" : "10%"
                    }}
                  />
                </div>
                <div className="analyst-progress-stages">
                  <span className={pipeline.stage === "analyzing" ? "active" : ""}>Analyze</span>
                  <span className={pipeline.stage === "scoring" ? "active" : ""}>Score</span>
                  <span className={pipeline.stage === "planning" ? "active" : ""}>Plan</span>
                  <span className={pipeline.stage === "chain_analysis" ? "active" : ""}>Chain</span>
                </div>
              </div>

              {(pipeline.iteration ?? 1) > 1 && (
                <div className="analyst-iteration-badge">
                  🔄 Iteration {pipeline.iteration} of {pipeline.max_iterations ?? 3}
                </div>
              )}
            </div>
          </div>
        )}

        {/* AWAITING APPROVAL: Show the layered report */}
        {isAwaitingApproval && pipeline && (
          <div className="analyst-approval-view">
            <div className="analyst-approval-header">
              <h2>📊 Impact Analysis Complete</h2>
              <p>Review the layered impact report below</p>
            </div>
            
            {pipeline.report ? (
              <div className="analyst-report-container">
                <pre className="analyst-report-text">{pipeline.report}</pre>
              </div>
            ) : (
              <div className="analyst-empty-state">
                <p>No report generated</p>
              </div>
            )}
            
            {pipeline.verification && (
              <div className="analyst-verification-summary">
                <h4>Verification Status</h4>
                <div className="analyst-verification-stats">
                  <span>Confidence: <strong>{pipeline.verification.confidence || "N/A"}</strong></span>
                  <span>Iterations: <strong>{pipeline.iteration}/{pipeline.max_iterations}</strong></span>
                  <span>Verified Paths: <strong>{pipeline.verification.verified_paths || 0}</strong></span>
                </div>
                {pipeline.verification.gaps && pipeline.verification.gaps.length > 0 && (
                  <div className="analyst-gaps-note">
                    ⚠️ {pipeline.verification.gaps.length} unresolved gaps
                  </div>
                )}
              </div>
            )}
            
            <div className="analyst-approval-actions">
              <button
                className="analyst-btn-primary analyst-btn-large"
                onClick={() => void handleApprove()}
                disabled={waiting}
              >
                ✅ Approve Analysis
              </button>
              <button
                className="analyst-btn-ghost"
                onClick={() => void handleReject()}
                disabled={waiting}
              >
                ❌ Reject
              </button>
            </div>
          </div>
        )}

        {/* COMPLETE STATES */}
        {isComplete && pipeline && (
          <div className="analyst-complete-screen">
            {pipeline.stage === "approved" ? (
              <>
                <div className="analyst-complete-icon">✅</div>
                <h2>Analysis Approved!</h2>
                <p>The task list is ready for implementation.</p>
              </>
            ) : (
              <>
                <div className="analyst-complete-icon">❌</div>
                <h2>Analysis Rejected</h2>
                <p>{pipeline.error || "You can start a new analysis."}</p>
              </>
            )}
            <button className="analyst-btn-primary" onClick={handleNewSession}>
              Start New Analysis
            </button>
          </div>
        )}
      </main>

      {/* ── RIGHT PANEL: IMPACT SUMMARY ── */}
      <aside className="analyst-panel analyst-impact-panel">
        <div className="analyst-panel-header">
          <span className="analyst-panel-title">Impact Summary</span>
        </div>

        {!pipeline || isGathering || isRequirementsReady ? (
          <div className="analyst-empty-state">
            <div className="analyst-empty-icon">🎯</div>
            <p>Impact details will appear here after analysis.</p>
          </div>
        ) : pipeline.report ? (
          <div className="analyst-impact-body">
            <div className="analyst-report-mini">
              <h4>Report Preview</h4>
              <pre className="analyst-report-preview">{pipeline.report.slice(0, 500)}...</pre>
              <p className="analyst-report-note">Full report shown in main panel</p>
            </div>
            {pipeline.verification && (
              <div className="analyst-verification-mini">
                <h4>Verification</h4>
                <p>Confidence: <strong>{pipeline.verification.confidence || "N/A"}</strong></p>
                <p>Iterations: <strong>{pipeline.iteration || 1}/{pipeline.max_iterations || 3}</strong></p>
              </div>
            )}
          </div>
        ) : (
          <div className="analyst-empty-state">
            <div className="analyst-empty-icon">⏳</div>
            <p>Analysis in progress...</p>
          </div>
        )}
      </aside>
    </div>
  );
}

// ─── SUB-COMPONENTS ───────────────────────────────────────────────────────────

function ChatBubble({ role, content }: { role: string; content: string }) {
  return (
    <div className={`analyst-message analyst-message--${role}`}>
      <div className="analyst-msg-avatar">{role === "user" ? "👤" : "🤖"}</div>
      <div className="analyst-msg-bubble">{content}</div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="analyst-message analyst-message--assistant">
      <div className="analyst-msg-avatar">🤖</div>
      <div className="analyst-msg-bubble analyst-msg-bubble--typing">
        <span className="analyst-typing-dot" />
        <span className="analyst-typing-dot" />
        <span className="analyst-typing-dot" />
      </div>
    </div>
  );
}

// Old components removed - using inline rendering now
