/**
 * downloadUtils.ts
 * Converts Forge cache entries into human-readable Markdown for download.
 */

// ─── Types ───────────────────────────────────────────────────────────────────

interface CacheEntry {
  id: string;
  pipeline_type: string;
  label: string;
  created_at: number | string;
  last_used_at: number | string;
  use_count: number | string;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
}

interface SpecSection {
  title?: string;
  content_md?: string;
  confidence?: number;
  gap_count?: number;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmtDate(ts: number | string): string {
  try {
    return new Date(Number(ts) * 1000).toLocaleString("en-GB", {
      day: "2-digit", month: "short", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return String(ts);
  }
}

function pct(v: number | undefined): string {
  return v !== undefined ? `${Math.round(v * 100)}%` : "—";
}

const TYPE_LABEL: Record<string, string> = {
  impact: "Impact Analysis",
  codegen: "Code Generation",
  reverse_engineer: "Reverse Engineer",
};

// ─── Per-type Markdown builders ───────────────────────────────────────────────

function impactToMd(entry: CacheEntry): string {
  const input = entry.input as {
    description?: string;
    services?: string[];
    functions?: string[];
    change_type?: string;
    constraints?: string[];
    clarity_score?: number;
  };
  const output = entry.output as { report?: string };

  const lines: string[] = [];

  lines.push(`# Impact Analysis Report`);
  lines.push(`\n**${entry.label}**\n`);
  lines.push(`| Field | Value |`);
  lines.push(`|---|---|`);
  lines.push(`| Generated | ${fmtDate(entry.created_at)} |`);
  lines.push(`| ID | \`${entry.id}\` |`);
  lines.push(`| Used | ${entry.use_count} time(s) |`);
  if (input.change_type) lines.push(`| Change Type | ${input.change_type} |`);
  if (input.clarity_score !== undefined) lines.push(`| Clarity Score | ${input.clarity_score}/10 |`);

  lines.push(`\n## Request\n`);
  lines.push(input.description || "—");

  if (input.services?.length) {
    lines.push(`\n**Target Services:** ${input.services.join(", ")}`);
  }
  if (input.functions?.length) {
    lines.push(`**Target Functions:** ${input.functions.join(", ")}`);
  }
  if (input.constraints?.length) {
    lines.push(`\n**Constraints:**`);
    input.constraints.forEach(c => lines.push(`- ${c}`));
  }

  lines.push(`\n---\n`);
  lines.push(`## Impact Report\n`);
  lines.push(output.report || "_No report generated._");

  return lines.join("\n");
}

function codegenToMd(entry: CacheEntry): string {
  const output = entry.output as {
    diffs?: Array<{ file?: string; task_id?: string; diff?: string; status?: string }>;
  };
  const input = entry.input as { change_request?: string; description?: string };
  const diffs = output.diffs || [];

  const lines: string[] = [];
  lines.push(`# Code Generation Report`);
  lines.push(`\n**${entry.label}**\n`);
  lines.push(`| Field | Value |`);
  lines.push(`|---|---|`);
  lines.push(`| Generated | ${fmtDate(entry.created_at)} |`);
  lines.push(`| ID | \`${entry.id}\` |`);
  lines.push(`| Files Changed | ${diffs.length} |`);

  lines.push(`\n## Change Request\n`);
  lines.push(input.change_request || input.description || "—");

  lines.push(`\n---\n`);
  lines.push(`## Generated Diffs\n`);

  if (diffs.length === 0) {
    lines.push("_No diffs saved._");
  } else {
    diffs.forEach((d, i) => {
      lines.push(`### ${i + 1}. \`${d.file || d.task_id || `diff-${i}`}\``);
      lines.push(`**Status:** ${d.status || "—"}\n`);
      lines.push("```diff");
      lines.push(d.diff || "(no diff content)");
      lines.push("```\n");
    });
  }

  return lines.join("\n");
}

function reToMd(entry: CacheEntry): string {
  const input = entry.input as { file_name?: string; user_comments?: string };
  const output = entry.output as {
    spec_sections?: Record<string, SpecSection>;
  };
  const sections = output.spec_sections || {};
  const sectionList = Object.entries(sections);

  const lines: string[] = [];
  lines.push(`# Reverse Engineer Specification`);
  lines.push(`\n**${entry.label}**\n`);
  lines.push(`| Field | Value |`);
  lines.push(`|---|---|`);
  lines.push(`| Generated | ${fmtDate(entry.created_at)} |`);
  lines.push(`| ID | \`${entry.id}\` |`);
  lines.push(`| Sections | ${sectionList.length} |`);
  if (input.file_name) lines.push(`| Log File | \`${input.file_name}\` |`);

  if (input.user_comments) {
    lines.push(`\n## User Context\n`);
    lines.push(input.user_comments);
  }

  lines.push(`\n---\n`);

  sectionList.forEach(([, sec]) => {
    const title = sec.title || "Section";
    const confidence = pct(sec.confidence);
    const gaps = sec.gap_count ? ` · ${sec.gap_count} gap(s)` : "";
    lines.push(`## ${title}`);
    lines.push(`*Confidence: ${confidence}${gaps}*\n`);
    lines.push(sec.content_md?.trim() || "_No content._");
    lines.push("\n---\n");
  });

  return lines.join("\n");
}

// ─── Public API ───────────────────────────────────────────────────────────────

export function entryToMarkdown(entry: CacheEntry): string {
  switch (entry.pipeline_type) {
    case "impact":          return impactToMd(entry);
    case "codegen":         return codegenToMd(entry);
    case "reverse_engineer": return reToMd(entry);
    default:                return `# ${entry.pipeline_type}\n\n\`\`\`json\n${JSON.stringify(entry, null, 2)}\n\`\`\``;
  }
}

export function triggerDownload(content: string | Blob, filename: string, mimeType = "text/markdown"): void {
  const blob = content instanceof Blob ? content : new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function safeFilename(label: string, suffix: string): string {
  const safe = label.replace(/[^a-z0-9_\-]/gi, "_").slice(0, 60);
  return `${safe}_${suffix}.md`;
}
