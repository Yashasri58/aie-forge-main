import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Send, Sparkles, Bot, User, ArrowLeft, PenLine } from "lucide-react";
import { Page, Header, Button, Spinner } from "../components/ui";
import { startPipeline, respondToPipeline, getPipelineStatus } from "../api";
import type { PipelineState, ChatMessage } from "../types";

export default function Chat() {
  const { pipelineId } = useParams();
  const navigate = useNavigate();
  
  const [pipeline, setPipeline] = useState<PipelineState | null>(null);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [initializing, setInitializing] = useState(false);
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);
  // True when user came back from the approval page to edit requirements
  const [isEditingMode, setIsEditingMode] = useState(false);
  
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Initialize or load pipeline
  useEffect(() => {
    if (pipelineId && pipelineId !== "new") {
      loadPipeline(pipelineId);
    }
  }, [pipelineId]);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [pipeline?.conversation_history, pendingMessage]);

  // Check if we should navigate to approval — but NOT when editing
  useEffect(() => {
    if (pipeline?.stage === "requirements_ready" && !isEditingMode) {
      navigate(`/approval/${pipeline.id}`);
    }
  }, [pipeline?.stage, pipeline?.id, navigate, isEditingMode]);

  async function loadPipeline(id: string) {
    try {
      const state = await getPipelineStatus(id);
      setPipeline(state);
      // If we land on chat with requirements_ready, we came from "Edit Requirements"
      if (state.stage === "requirements_ready") {
        setIsEditingMode(true);
      }
    } catch (err) {
      console.error("Failed to load pipeline:", err);
      navigate("/");
    }
  }

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || sending) return;

    setInput("");
    setSending(true);
    setPendingMessage(text);
    // Once user sends a message in edit mode, they're actively editing
    // The auto-redirect suppression stays until requirements are ready again
    if (isEditingMode) setIsEditingMode(false);

    try {
      let state: PipelineState;
      
      if (!pipeline) {
        setInitializing(true);
        state = await startPipeline(text);
        setInitializing(false);
        window.history.replaceState(null, "", `/chat/${state.id}`);
      } else {
        state = await respondToPipeline(pipeline.id, text);
      }
      
      setPipeline(state);
      setPendingMessage(null);
    } catch (err) {
      console.error("Failed to send message:", err);
      setPendingMessage(null);
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  }, [input, sending, pipeline, isEditingMode]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const messages = pipeline?.conversation_history || [];
  const currentQuestion = pipeline?.current_question;

  return (
    <Page className="flex flex-col">
      <Header
        backTo="/"
        backLabel="Dashboard"
        step={{ current: 1, total: 4, label: "Gathering" }}
      />

      {/* Chat Container */}
      <div className="flex-1 flex flex-col min-h-0 max-w-4xl mx-auto w-full">

        {/* Edit mode banner — shown when returning from approval page */}
        {isEditingMode && pipeline && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-4 px-4 py-3 rounded-xl border border-[var(--color-accent)] bg-[var(--color-accent-subtle)] flex items-start gap-3"
          >
            <PenLine size={18} className="text-[var(--color-accent)] mt-0.5 shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-[var(--color-accent)]">Editing requirements</p>
              <p className="text-sm text-[var(--color-text-secondary)] mt-0.5">
                Tell me what you'd like to change. The agent will continue and update the requirements.
              </p>
            </div>
            <button
              onClick={() => navigate(`/approval/${pipeline.id}`)}
              className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] flex items-center gap-1 shrink-0 mt-0.5"
            >
              <ArrowLeft size={12} />
              Back to review
            </button>
          </motion.div>
        )}

        {/* Messages Area */}
        <div className="flex-1 overflow-y-auto py-6 space-y-4">
          {/* Welcome message when empty */}
          {messages.length === 0 && !initializing && !pendingMessage && (
            <motion.div
              className="flex flex-col items-center justify-center h-full text-center px-8"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
            >
              <div className="w-20 h-20 rounded-2xl bg-[var(--color-accent-subtle)] flex items-center justify-center mb-6">
                <Sparkles size={36} className="text-[var(--color-accent)]" />
              </div>
              <h2 className="text-2xl font-semibold text-[var(--color-text-primary)] mb-3">
                What changes are you planning?
              </h2>
              <p className="text-[var(--color-text-secondary)] max-w-md mb-8">
                Describe what you want to build, change, or modify. I'll help you understand
                the impact across your codebase.
              </p>
              <div className="flex flex-wrap gap-2 justify-center">
                {[
                  "Add retry logic to payment gateway",
                  "Deprecate the old auth endpoint",
                  "Add logging to all API calls",
                ].map((suggestion) => (
                  <button
                    key={suggestion}
                    onClick={() => setInput(suggestion)}
                    className="px-4 py-2 text-sm rounded-full bg-[var(--color-bg-elevated)] border border-[var(--color-glass-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:border-[var(--color-accent)] transition-all"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </motion.div>
          )}

          {/* Initializing state */}
          {initializing && messages.length === 0 && (
            <motion.div
              className="flex flex-col items-center justify-center h-full"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
            >
              <Spinner size="lg" />
              <p className="mt-4 text-[var(--color-text-muted)]">
                Starting analysis...
              </p>
            </motion.div>
          )}

          {/* Messages */}
          <AnimatePresence mode="popLayout">
            {messages.map((msg, i) => (
              <ChatBubble key={i} message={msg} />
            ))}
          </AnimatePresence>

          {/* Pending user message (optimistic UI) */}
          {pendingMessage && (
            <ChatBubble
              message={{ role: "user", content: pendingMessage }}
            />
          )}

          {/* Current question (if different from last message) */}
          {currentQuestion && 
           messages.length > 0 && 
           messages[messages.length - 1]?.content !== currentQuestion && (
            <ChatBubble
              message={{ role: "assistant", content: currentQuestion }}
            />
          )}

          {/* Typing indicator */}
          {sending && (
            <motion.div
              className="flex items-start gap-3"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
            >
              <div className="w-8 h-8 rounded-full bg-[var(--color-bg-elevated)] flex items-center justify-center flex-shrink-0">
                <Bot size={16} className="text-[var(--color-accent)]" />
              </div>
              <div className="chat-bubble chat-bubble-assistant">
                <TypingIndicator />
              </div>
            </motion.div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <div className="border-t border-[var(--color-glass-border)] pt-4 pb-2">
          <div className="relative">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Describe what you want to change..."
              className="input min-h-[56px] max-h-[200px] pr-14 resize-none"
              rows={1}
              disabled={sending || initializing}
              style={{
                height: "auto",
                minHeight: "56px",
              }}
              onInput={(e) => {
                const target = e.target as HTMLTextAreaElement;
                target.style.height = "auto";
                target.style.height = Math.min(target.scrollHeight, 200) + "px";
              }}
            />
            <Button
              variant="primary"
              size="sm"
              className="absolute right-2 bottom-2 !p-2"
              onClick={handleSend}
              disabled={!input.trim() || sending}
              icon={<Send size={16} />}
            >
              <span className="sr-only">Send</span>
            </Button>
          </div>
          <p className="text-xs text-[var(--color-text-muted)] mt-2 text-center">
            Press Enter to send, Shift + Enter for new line
          </p>
        </div>
      </div>
    </Page>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   Sub-components
   ═══════════════════════════════════════════════════════════════════════════ */

function ChatBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  return (
    <motion.div
      className={`flex items-start gap-3 ${isUser ? "flex-row-reverse" : ""}`}
      initial={{ opacity: 0, y: 10, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.98 }}
      transition={{ duration: 0.2 }}
    >
      <div
        className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
          isUser
            ? "bg-[var(--color-accent)]"
            : "bg-[var(--color-bg-elevated)] border border-[var(--color-glass-border)]"
        }`}
      >
        {isUser ? (
          <User size={16} className="text-white" />
        ) : (
          <Bot size={16} className="text-[var(--color-accent)]" />
        )}
      </div>
      <div
        className={`chat-bubble ${
          isUser ? "chat-bubble-user" : "chat-bubble-assistant"
        }`}
      >
        <p className="whitespace-pre-wrap">{message.content}</p>
      </div>
    </motion.div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1 py-1">
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          className="w-2 h-2 rounded-full bg-[var(--color-text-muted)]"
          animate={{ opacity: [0.4, 1, 0.4] }}
          transition={{
            duration: 1,
            repeat: Infinity,
            delay: i * 0.2,
          }}
        />
      ))}
    </div>
  );
}
