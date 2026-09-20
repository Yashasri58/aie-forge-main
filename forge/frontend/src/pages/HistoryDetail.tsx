import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowLeft, Clock, Database, FileText, Code, Search } from "lucide-react";
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
    <Page>
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
        <pre className="text-xs text-[var(--color-text-secondary)] whitespace-pre-wrap leading-relaxed font-mono overflow-auto max-h-[60vh]">
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
              <div className="p-4 text-sm text-[var(--color-text-secondary)] leading-relaxed max-h-64 overflow-auto">
                <pre className="whitespace-pre-wrap font-sans">
                  {sec.content_md?.slice(0, 800) || ""}
                  {(sec.content_md?.length || 0) > 800 ? "\n\n… (truncated)" : ""}
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
