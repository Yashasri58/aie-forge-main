import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowLeft, Clock, Database, FileText, Code, Search, ChevronDown, ChevronRight } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Page, Card, Badge, Button } from "../components/ui";

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
}

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
  const [activeSection, setActiveSection] = useState<"input" | "output">("output");

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
    <Page>
      {/* Header */}
      <header className="flex items-center justify-between pb-6 border-b border-[var(--color-glass-border)] mb-6">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate(-1)}
            className="flex items-center gap-2 text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
          >
            <ArrowLeft size={16} />
            Past Requests &amp; Results
          </button>
          <span className="text-[var(--color-glass-border)]">/</span>
          <span className="text-sm text-[var(--color-text-primary)] font-medium truncate max-w-xs">
            {entry.label}
          </span>
        </div>
        <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium ${typeConf.bg} ${typeConf.color}`}>
          {typeConf.icon}
          {typeConf.label}
        </div>
      </header>

      {/* Meta row */}
      <motion.div
        className="flex flex-wrap items-center gap-6 mb-6 text-sm text-[var(--color-text-muted)]"
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
        <Badge variant="accent">ID: {entry.id.slice(0, 8)}…</Badge>
      </motion.div>

      {/* Tab selector */}
      <div className="flex gap-1 mb-4 p-1 bg-[var(--color-glass-bg)] rounded-xl w-fit border border-[var(--color-glass-border)]">
        {(["output", "input"] as const).map((tab) => (
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

/* ── Markdown renderer ────────────────────────────────────────────────────── */
function MarkdownView({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        h1: ({ children }) => (
          <h1 className="text-xl font-bold text-[var(--color-text-primary)] mt-6 mb-3 pb-2 border-b border-[var(--color-glass-border)]">{children}</h1>
        ),
        h2: ({ children }) => (
          <h2 className="text-lg font-semibold text-[var(--color-text-primary)] mt-5 mb-2">{children}</h2>
        ),
        h3: ({ children }) => (
          <h3 className="text-base font-semibold text-[var(--color-text-primary)] mt-4 mb-2">{children}</h3>
        ),
        h4: ({ children }) => (
          <h4 className="text-sm font-semibold text-[var(--color-text-muted)] uppercase tracking-wide mt-3 mb-1">{children}</h4>
        ),
        p: ({ children }) => (
          <p className="text-sm text-[var(--color-text-secondary)] leading-relaxed mb-3">{children}</p>
        ),
        ul: ({ children }) => (
          <ul className="list-disc list-inside space-y-1 mb-3 text-sm text-[var(--color-text-secondary)]">{children}</ul>
        ),
        ol: ({ children }) => (
          <ol className="list-decimal list-inside space-y-1 mb-3 text-sm text-[var(--color-text-secondary)]">{children}</ol>
        ),
        li: ({ children }) => (
          <li className="text-sm text-[var(--color-text-secondary)] leading-relaxed">{children}</li>
        ),
        code: ({ className, children, ...props }) => {
          const isInline = !className;
          return isInline ? (
            <code className="px-1.5 py-0.5 rounded bg-[var(--color-glass-border)] text-[var(--color-accent)] text-xs font-mono" {...props}>
              {children}
            </code>
          ) : (
            <code className="block bg-[var(--color-glass-bg)] border border-[var(--color-glass-border)] rounded-lg p-3 text-xs font-mono text-[var(--color-text-secondary)] whitespace-pre-wrap overflow-auto" {...props}>
              {children}
            </code>
          );
        },
        pre: ({ children }) => (
          <div className="mb-3">{children}</div>
        ),
        blockquote: ({ children }) => (
          <blockquote className="border-l-2 border-[var(--color-accent)] pl-3 my-3 text-sm text-[var(--color-text-muted)] italic">
            {children}
          </blockquote>
        ),
        table: ({ children }) => (
          <div className="overflow-auto mb-3">
            <table className="w-full text-sm border-collapse">{children}</table>
          </div>
        ),
        thead: ({ children }) => (
          <thead className="border-b border-[var(--color-glass-border)]">{children}</thead>
        ),
        th: ({ children }) => (
          <th className="text-left px-3 py-1.5 text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide">{children}</th>
        ),
        td: ({ children }) => (
          <td className="px-3 py-1.5 text-[var(--color-text-secondary)] border-b border-[var(--color-glass-border)]">{children}</td>
        ),
        hr: () => (
          <hr className="my-4 border-[var(--color-glass-border)]" />
        ),
        strong: ({ children }) => (
          <strong className="font-semibold text-[var(--color-text-primary)]">{children}</strong>
        ),
        em: ({ children }) => (
          <em className="italic text-[var(--color-text-muted)]">{children}</em>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
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

  /* ── Impact: markdown report ─────────────────────────────────────────── */
  if (entry.pipeline_type === "impact") {
    const report = (output.report as string) || "";
    if (!report) {
      return (
        <Card className="p-5">
          <p className="text-sm text-[var(--color-text-muted)]">No report saved</p>
        </Card>
      );
    }
    return (
      <Card className="p-6 overflow-auto max-h-[calc(100vh-280px)]">
        <MarkdownView content={report} />
      </Card>
    );
  }

  /* ── CodeGen: unified diffs ──────────────────────────────────────────── */
  if (entry.pipeline_type === "codegen") {
    const diffs = (output.diffs as Array<{ file?: string; task_id?: string; diff?: string; status?: string }>) || [];
    return (
      <div className="space-y-4 overflow-auto max-h-[calc(100vh-280px)]">
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

  /* ── Reverse Engineer: spec sections ─────────────────────────────────── */
  if (entry.pipeline_type === "reverse_engineer") {
    return <REOutputView output={output} />;
  }

  return <JsonBlock data={output} />;
}

/* ── Reverse Engineer output — all sections, collapsible, full markdown ── */
type SpecSectionData = {
  title?: string;
  content_md?: string;
  confidence_score?: number;
  gap_count?: number;
  section_id?: string;
};

function REOutputView({ output }: { output: Record<string, unknown> }) {
  const sections = (output.spec_sections as Record<string, SpecSectionData>) || {};
  const sectionList = Object.entries(sections);
  const [openSections, setOpenSections] = useState<Set<string>>(
    () => new Set(sectionList.map(([k]) => k))  // all open by default
  );

  function toggle(key: string) {
    setOpenSections(prev => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  }

  if (sectionList.length === 0) {
    return (
      <Card className="p-5">
        <p className="text-sm text-[var(--color-text-muted)]">No spec sections saved</p>
      </Card>
    );
  }

  const totalSections = sectionList.length;
  const avgConfidence = sectionList.reduce((sum, [, sec]) => sum + (sec.confidence_score ?? 0), 0) / totalSections;

  return (
    <div className="space-y-3 overflow-auto max-h-[calc(100vh-280px)]">
      {/* Summary bar */}
      <div className="flex items-center gap-4 px-1 mb-2 text-xs text-[var(--color-text-muted)]">
        <span>{totalSections} sections</span>
        <span>·</span>
        <span>avg confidence: <span className="text-[var(--color-accent)]">{Math.round(avgConfidence * 100)}%</span></span>
        <button
          className="ml-auto text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
          onClick={() => setOpenSections(openSections.size === totalSections ? new Set() : new Set(sectionList.map(([k]) => k)))}
        >
          {openSections.size === totalSections ? "Collapse all" : "Expand all"}
        </button>
      </div>

      {sectionList.map(([key, sec], i) => {
        const isOpen = openSections.has(key);
        const confidence = sec.confidence_score ?? 0;
        const confPct = Math.round(confidence * 100);
        const confColor = confidence >= 0.7 ? "text-green-400" : confidence >= 0.4 ? "text-yellow-400" : "text-red-400";

        return (
          <motion.div
            key={key}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.03 }}
          >
            <Card className="overflow-hidden">
              {/* Section header — clickable */}
              <button
                onClick={() => toggle(key)}
                className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-[var(--color-glass-bg)] transition-colors"
              >
                <span className="text-[var(--color-text-muted)] shrink-0">
                  {isOpen ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                </span>

                <span className="flex-1 text-sm font-semibold text-[var(--color-text-primary)]">
                  {sec.title || key.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())}
                </span>

                <div className="flex items-center gap-2 shrink-0">
                  {sec.gap_count !== undefined && sec.gap_count > 0 && (
                    <Badge variant="default">{sec.gap_count} gap{sec.gap_count !== 1 ? "s" : ""}</Badge>
                  )}
                  {sec.confidence_score !== undefined && (
                    <span className={`text-xs font-mono font-bold ${confColor}`}>
                      {confPct}%
                    </span>
                  )}
                </div>
              </button>

              {/* Section body — full markdown, no truncation */}
              {isOpen && (
                <div className="border-t border-[var(--color-glass-border)] px-6 py-4 bg-[var(--color-bg-elevated)]">
                  {sec.content_md ? (
                    <MarkdownView content={sec.content_md} />
                  ) : (
                    <p className="text-sm text-[var(--color-text-muted)]">No content available</p>
                  )}
                </div>
              )}
            </Card>
          </motion.div>
        );
      })}
    </div>
  );
}

/* ── JSON fallback ────────────────────────────────────────────────────── */
function JsonBlock({ data }: { data: unknown }) {
  return (
    <Card className="p-4">
      <pre className="text-xs font-mono text-[var(--color-text-secondary)] whitespace-pre-wrap overflow-auto max-h-96">
        {JSON.stringify(data, null, 2)}
      </pre>
    </Card>
  );
}
