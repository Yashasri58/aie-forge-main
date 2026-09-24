import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowLeft, Clock, Database, FileText, Code, Search, Zap, ChevronDown, ChevronRight } from "lucide-react";
import { Page, Card, Badge, Button } from "../components/ui";
import { entryToMarkdown, triggerDownload, safeFilename } from "../utils/downloadUtils";
import type { TokenUsage, TokenUsageByModel } from "../api";

interface HistoryEntry {
  id: string;
  pipeline_type: "impact" | "codegen" | "reverse_engineer";
  label: string;
  created_at: number;
  last_used_at: number;
  use_count: number;
  has_output: boolean;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  token_usage?: TokenUsage;
}

// ─── Formatting helpers ────────────────────────────────────────────────────

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function formatCost(usd: number): string {
  if (usd === 0) return "$0.00";
  if (usd < 0.0001) return `$${usd.toExponential(2)}`;
  if (usd < 0.01) return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(3)}`;
}

// ─── Token Usage Panel ─────────────────────────────────────────────────────

function TokenPanel({ usage }: { usage: TokenUsage | undefined; entry?: HistoryEntry }) {
  const [expanded, setExpanded] = useState(false);

  const hasReal = usage && usage.totals && usage.totals.calls > 0;

  // For old entries without real data — show a subtle "no data" hint
  if (!hasReal) {
    return (
      <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[var(--color-glass-bg)] border border-[var(--color-glass-border)] text-[10px] text-[var(--color-text-muted)]"
        title="Token tracking was added after this entry was created. Re-run this analysis to see real token counts.">
        <Zap size={11} className="opacity-30" />
        No token data · re-run to track
      </span>
    );
  }

  const { totals, by_model } = usage!;
  const modelEntries = Object.entries(by_model) as [string, TokenUsageByModel][];

  return (
    <div className="flex flex-col gap-2">
      {/* Summary pill — always visible */}
      <button
        onClick={() => setExpanded(e => !e)}
        className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[var(--color-glass-bg)] border border-[var(--color-glass-border)] text-xs hover:border-[var(--color-accent)] transition-colors"
        title="Click to see pricing breakdown"
      >
        <Zap size={13} className="text-[var(--color-accent)]" />
        <span className="font-semibold text-[var(--color-text-primary)]">
          {formatTokens(totals.input_tokens + totals.output_tokens)}
        </span>
        <span className="text-[var(--color-text-muted)]">tokens</span>
        <span className="text-[var(--color-text-muted)] opacity-60">·</span>
        <span className="text-[var(--color-text-primary)] font-semibold">{formatCost(totals.cost_usd)}</span>
        {expanded
          ? <ChevronDown size={11} className="text-[var(--color-text-muted)] ml-1" />
          : <ChevronRight size={11} className="text-[var(--color-text-muted)] ml-1" />}
      </button>

      {/* Expanded breakdown */}
      {expanded && (
        <motion.div
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.15 }}
          className="rounded-xl border border-[var(--color-glass-border)] bg-[var(--color-glass-bg)] overflow-hidden text-xs"
        >
          {/* Totals row */}
          <div className="flex items-center gap-6 px-4 py-2.5 border-b border-[var(--color-glass-border)] bg-[var(--color-bg-elevated)]">
            <span className="font-semibold text-[var(--color-text-primary)] uppercase tracking-wider text-[10px]">Total</span>
            <span className="text-[var(--color-text-secondary)]">
              <span className="font-mono text-[var(--color-text-primary)]">{formatTokens(totals.input_tokens)}</span> in
            </span>
            <span className="text-[var(--color-text-secondary)]">
              <span className="font-mono text-[var(--color-text-primary)]">{formatTokens(totals.output_tokens)}</span> out
            </span>
            {totals.reasoning_tokens > 0 && (
              <span className="text-[var(--color-text-secondary)]" title="Thinking tokens billed at output rate (separate from output text)">
                <span className="font-mono text-purple-400">{formatTokens(totals.reasoning_tokens)}</span>
                <span className="text-purple-400/70"> thinking</span>
              </span>
            )}
            <span className="text-[var(--color-text-secondary)]">
              <span className="font-mono text-[var(--color-text-primary)]">{totals.calls}</span> calls
            </span>
            <span className="ml-auto font-semibold text-[var(--color-accent)]">{formatCost(totals.cost_usd)}</span>
          </div>

          {/* Per-model rows */}
          {modelEntries.map(([model, m]) => (
            <div key={model} className="flex items-center gap-4 px-4 py-2 border-b last:border-0 border-[var(--color-glass-border)]">
              <span className="font-mono text-[var(--color-text-primary)] w-40 truncate" title={model}>{model}</span>
              <div className="flex flex-col gap-0.5">
                <span className="text-[var(--color-text-muted)]">
                  <span className="font-mono text-[var(--color-text-secondary)]">{formatTokens(m.input_tokens)}</span> in ·{" "}
                  <span className="font-mono text-[var(--color-text-secondary)]">{formatTokens(m.output_tokens)}</span> out
                  {m.reasoning_tokens > 0 && (
                    <> · <span className="font-mono text-purple-400">{formatTokens(m.reasoning_tokens)}</span> <span className="text-purple-400/70">thinking</span></>
                  )}
                </span>
                <span className="text-[var(--color-text-muted)] text-[10px]">
                  ${m.price_input_per_m.toFixed(2)}/M in · ${m.price_output_per_m.toFixed(2)}/M out+thinking
                </span>
              </div>
              <span className="ml-auto font-mono text-[var(--color-text-primary)]">{formatCost(m.cost_usd)}</span>
            </div>
          ))}
        </motion.div>
      )}
    </div>
  );
}

// Per pipeline type: which fields are the main LLM content.
// (Kept as fallback for old entries without real token_usage data)

const TYPE_CONFIG = {
  impact: {
    icon: <Search size={18} />,
    label: "Impact Analysis",
    color: "text-blue-400",
    bg: "bg-blue-400/10",
  },
  codegen: {
    icon: <Code size={18} />,
    label: "Code Generation",
    color: "text-green-400",
    bg: "bg-green-400/10",
  },
  reverse_engineer: {
    icon: <FileText size={18} />,
    label: "Reverse Engineer",
    color: "text-purple-400",
    bg: "bg-purple-400/10",
  },
};

export default function HistoryDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [entry, setEntry] = useState<HistoryEntry | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState<"input" | "output">("input");

  useEffect(() => {
    if (!id) return;
    fetch(`/cache/${encodeURIComponent(id)}`)
      .then((r) => {
        if (!r.ok) throw new Error("Not found");
        return r.json();
      })
      .then(setEntry)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  const fmt = (ts: number) =>
    new Date(ts * 1000).toLocaleString("en-GB", {
      day: "2-digit", month: "short", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });

  if (loading) {
    return (
      <Page>
        <div className="flex items-center justify-center h-64">
          <div className="shimmer w-full max-w-lg h-12 rounded-lg" />
        </div>
      </Page>
    );
  }

  if (error || !entry) {
    return (
      <Page>
        <div className="flex flex-col items-center justify-center h-64 gap-4">
          <p className="text-[var(--color-text-muted)]">Entry not found</p>
          <Button variant="ghost" onClick={() => navigate(-1)} icon={<ArrowLeft size={16} />}>Back</Button>
        </div>
      </Page>
    );
  }

  const typeConf = TYPE_CONFIG[entry.pipeline_type] || TYPE_CONFIG.impact;

  return (
    <Page scrollable>
      {/* Header */}
      <header className="flex items-center justify-between pb-6 border-b border-[var(--color-glass-border)] mb-6">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate(-1)}
            className="flex items-center gap-2 text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
          >
            <ArrowLeft size={16} />
            Past Requests & Results
          </button>
          <span className="text-[var(--color-glass-border)]">/</span>
          <span className="text-sm text-[var(--color-text-primary)] font-medium truncate max-w-xs">
            {entry.label?.replace(/^\[REJECTED\]\s*/, "") ?? ""}
          </span>
          {entry.label?.startsWith("[REJECTED]") && (
            <span className="flex-shrink-0 px-2 py-0.5 rounded text-xs font-bold bg-[var(--color-error-subtle)] text-[var(--color-error)] border border-[var(--color-error)]">
              REJECTED
            </span>
          )}
        </div>
        <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium ${typeConf.bg} ${typeConf.color}`}>
          {typeConf.icon}
          {typeConf.label}
        </div>
        <button
          onClick={() => {
            const md = entryToMarkdown(entry as Parameters<typeof entryToMarkdown>[0]);
            triggerDownload(md, safeFilename(entry.label, entry.id.slice(0, 8)));
          }}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-[var(--color-glass-bg)] border border-[var(--color-glass-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-accent)] hover:border-[var(--color-accent)] transition-all ml-2"
          title="Download as Markdown"
        >
          <Zap size={13} className="opacity-60" />
          Download .md
        </button>
      </header>

      {/* Meta row */}
      <motion.div
        className="flex flex-wrap items-center gap-4 mb-6 text-sm text-[var(--color-text-muted)]"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <span className="flex items-center gap-1.5">
          <Clock size={14} />
          {fmt(entry.created_at)}
        </span>
        <span className="flex items-center gap-1.5">
          <Database size={14} />
          Used {entry.use_count} time{entry.use_count !== 1 ? "s" : ""}
        </span>
        {/* Real token usage + pricing */}
        <TokenPanel usage={entry.token_usage} entry={entry} />
        <Badge variant="accent">ID: {entry.id.slice(0, 8)}…</Badge>
      </motion.div>

      {/* Tab selector */}
      <div className="flex gap-1 mb-4 p-1 bg-[var(--color-glass-bg)] rounded-xl w-fit border border-[var(--color-glass-border)]">
        {(["input", "output"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveSection(tab)}
            className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-all ${
              activeSection === tab
                ? "bg-[var(--color-accent)] text-white"
                : "text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
            }`}
          >
            {tab === "input" ? "Request" : "Result"}
          </button>
        ))}
      </div>

      {/* Content */}
      <motion.div
        key={activeSection}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.15 }}
      >
        {activeSection === "input" ? (
          <InputView entry={entry} />
        ) : (
          <OutputView entry={entry} />
        )}
      </motion.div>
    </Page>
  );
}

/* ── Input view ─────────────────────────────────────────────────────────── */
function InputView({ entry }: { entry: HistoryEntry }) {
  const input = entry.input as Record<string, unknown>;

  if (entry.pipeline_type === "impact" || entry.pipeline_type === "codegen") {
    const req = input as {
      change_request?: string;
      description?: string;
      services?: string[];
      functions?: string[];
      constraints?: string[];
      change_type?: string;
    };
    return (
      <div className="space-y-4">
        <Card className="p-5">
          <h3 className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wider mb-3">
            Change Request
          </h3>
          <p className="text-sm text-[var(--color-text-primary)] leading-relaxed">
            {req.change_request || req.description || "—"}
          </p>
        </Card>
        {req.services && req.services.length > 0 && (
          <Card className="p-5">
            <h3 className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wider mb-3">
              Target Services
            </h3>
            <div className="flex flex-wrap gap-2">
              {req.services.map((s) => (
                <Badge key={s} variant="accent">{s}</Badge>
              ))}
            </div>
          </Card>
        )}
        {req.constraints && req.constraints.length > 0 && (
          <Card className="p-5">
            <h3 className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wider mb-3">
              Constraints
            </h3>
            <ul className="space-y-1">
              {req.constraints.map((c, i) => (
                <li key={i} className="text-sm text-[var(--color-text-primary)]">• {c}</li>
              ))}
            </ul>
          </Card>
        )}
        {req.change_type && (
          <Card className="p-5">
            <h3 className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wider mb-3">
              Change Type
            </h3>
            <Badge variant="accent">{req.change_type}</Badge>
          </Card>
        )}
      </div>
    );
  }

  if (entry.pipeline_type === "reverse_engineer") {
    const req = input as { file_name?: string; user_comments?: string };
    return (
      <div className="space-y-4">
        <Card className="p-5">
          <h3 className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wider mb-3">
            Log File
          </h3>
          <p className="text-sm font-mono text-[var(--color-accent)]">{req.file_name || "—"}</p>
        </Card>
        {req.user_comments && (
          <Card className="p-5">
            <h3 className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wider mb-3">
              User Context
            </h3>
            <p className="text-sm text-[var(--color-text-primary)] leading-relaxed">{req.user_comments}</p>
          </Card>
        )}
      </div>
    );
  }

  return <JsonBlock data={input} />;
}

/* ── Output view ────────────────────────────────────────────────────────── */
function OutputView({ entry }: { entry: HistoryEntry }) {
  const output = entry.output as Record<string, unknown>;

  if (entry.pipeline_type === "impact") {
    const report = (output.report as string) || "";
    return (
      <Card className="p-5">
        <h3 className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wider mb-3">
          Impact Report
        </h3>
        <pre className="text-xs text-[var(--color-text-secondary)] whitespace-pre-wrap leading-relaxed font-mono overflow-auto">
          {report || "No report saved"}
        </pre>
      </Card>
    );
  }

  if (entry.pipeline_type === "codegen") {
    const diffs = (output.diffs as Array<{ file?: string; task_id?: string; diff?: string; status?: string }>) || [];
    return (
      <div className="space-y-4">
        {diffs.length === 0 ? (
          <Card className="p-5">
            <p className="text-sm text-[var(--color-text-muted)]">No diffs saved</p>
          </Card>
        ) : (
          diffs.map((d, i) => (
            <Card key={i} className="overflow-hidden">
              <div className="flex items-center justify-between px-4 py-2.5 border-b border-[var(--color-glass-border)] bg-[var(--color-glass-bg)]">
                <span className="text-xs font-mono text-[var(--color-text-primary)]">
                  {d.file || d.task_id || `diff-${i}`}
                </span>
                <Badge variant={d.status === "success" ? "accent" : "default"}>{d.status || "—"}</Badge>
              </div>
              <pre className="p-4 text-xs font-mono whitespace-pre-wrap overflow-auto max-h-96 text-[var(--color-text-secondary)]">
                {d.diff || "No diff content"}
              </pre>
            </Card>
          ))
        )}
      </div>
    );
  }

  if (entry.pipeline_type === "reverse_engineer") {
    const sections = (output.spec_sections as Record<string, { title?: string; content_md?: string; confidence?: number; gap_count?: number }>) || {};
    const sectionList = Object.entries(sections);
    return (
      <div className="space-y-4">
        {sectionList.length === 0 ? (
          <Card className="p-5">
            <p className="text-sm text-[var(--color-text-muted)]">No spec sections saved</p>
          </Card>
        ) : (
          sectionList.map(([key, sec]) => (
            <Card key={key} className="overflow-hidden">
              <div className="flex items-center justify-between px-4 py-2.5 border-b border-[var(--color-glass-border)] bg-[var(--color-glass-bg)]">
                <span className="text-sm font-medium text-[var(--color-text-primary)]">
                  {sec.title || key.replace(/_/g, " ")}
                </span>
                <div className="flex items-center gap-2">
                  {sec.confidence !== undefined && (
                    <Badge variant="accent">{Math.round(sec.confidence * 100)}%</Badge>
                  )}
                  {sec.gap_count !== undefined && sec.gap_count > 0 && (
                    <Badge variant="default">{sec.gap_count}g</Badge>
                  )}
                </div>
              </div>
              <div className="p-4 text-sm text-[var(--color-text-secondary)] leading-relaxed overflow-auto">
                <pre className="whitespace-pre-wrap font-sans">
                  {sec.content_md || ""}
                </pre>
              </div>
            </Card>
          ))
        )}
      </div>
    );
  }

  return <JsonBlock data={output} />;
}

function JsonBlock({ data }: { data: unknown }) {
  return (
    <Card className="p-4">
      <pre className="text-xs font-mono text-[var(--color-text-secondary)] whitespace-pre-wrap overflow-auto max-h-96">
        {JSON.stringify(data, null, 2)}
      </pre>
    </Card>
  );
}
