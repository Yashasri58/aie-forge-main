/**
 * RESpec — Spec viewer page for the Reverse Engineer pipeline.
 *
 * Tabbed view of all 11 spec sections.
 * Renders Markdown with confidence badges ([CONFIRMED] / [INFERRED] / [GAP]).
 * Sidebar shows overall confidence + gap count.
 * Download button for zip of all markdown files.
 */

import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import { getREStatus, downloadRESpec } from "../api";
import type { ReverseEngineerSession, SpecSection, RESectionId } from "../types";
import { RE_SECTION_IDS } from "../types";
import ConfidenceBadge from "../components/ConfidenceBadge";

// ─── Section metadata ─────────────────────────────────────────────────────────

const SECTION_META: Record<string, { title: string; icon: string }> = {
  executive_summary:      { title: "Executive Summary",        icon: "📋" },
  service_inventory:      { title: "Service Inventory",        icon: "🏗️" },
  api_catalog:            { title: "API Catalog",              icon: "🔌" },
  business_logic:         { title: "Business Logic",           icon: "⚙️" },
  event_topology:         { title: "Event Topology",           icon: "📨" },
  data_model:             { title: "Data Model",               icon: "🗄️" },
  cross_cutting:          { title: "Cross-Cutting Concerns",   icon: "🔒" },
  slos_and_observability: { title: "SLOs & Observability",    icon: "📊" },
  resilience_patterns:    { title: "Resilience Patterns",      icon: "🛡️" },
  tech_stack:             { title: "Tech Stack",               icon: "🧰" },
  risks_and_gaps:         { title: "Risks & Gaps",             icon: "⚠️" },
  confidence_report:      { title: "Confidence Report",        icon: "🎯" },
};

// ─── Simple Markdown renderer ─────────────────────────────────────────────────
// Renders headings, bold, italic, code blocks, tables, and confidence tags.

function renderMarkdown(md: string): string {
  let html = md
    // Code blocks
    .replace(/```(\w*)\n([\s\S]*?)```/g, (_match, _lang, code) =>
      `<pre class="bg-black/50 rounded-lg p-4 overflow-x-auto text-xs text-emerald-300 my-3 border border-white/10"><code>${escapeHtml(code.trim())}</code></pre>`
    )
    // Inline code
    .replace(/`([^`]+)`/g, '<code class="bg-white/10 rounded px-1 py-0.5 text-xs font-mono text-emerald-300">$1</code>')
    // Confidence tags — style them
    .replace(/\*\*\[CONFIRMED\]\*\*/g, '<span class="inline-flex items-center px-1.5 py-0.5 rounded border border-emerald-600/50 bg-emerald-900/40 text-emerald-300 text-[10px] font-mono font-semibold">[CONFIRMED]</span>')
    .replace(/\*\*\[INFERRED\]\*\*/g, '<span class="inline-flex items-center px-1.5 py-0.5 rounded border border-amber-600/50 bg-amber-900/40 text-amber-300 text-[10px] font-mono font-semibold">[INFERRED]</span>')
    .replace(/\*\*\[GAP\]\*\*/g, '<span class="inline-flex items-center px-1.5 py-0.5 rounded border border-red-600/50 bg-red-900/40 text-red-300 text-[10px] font-mono font-semibold">[GAP]</span>')
    // Bold
    .replace(/\*\*([^*]+)\*\*/g, '<strong class="text-white font-semibold">$1</strong>')
    // Italic
    .replace(/\*([^*]+)\*/g, '<em class="text-gray-300 italic">$1</em>')
    // H3
    .replace(/^### (.+)$/gm, '<h3 class="text-base font-semibold text-white mt-5 mb-2">$1</h3>')
    // H2
    .replace(/^## (.+)$/gm, '<h2 class="text-lg font-bold text-white mt-6 mb-3">$1</h2>')
    // H1
    .replace(/^# (.+)$/gm, '<h1 class="text-xl font-bold text-white mt-6 mb-3">$1</h1>')
    // Horizontal rule
    .replace(/^---$/gm, '<hr class="border-white/10 my-4" />')
    // Blockquotes (gap/inferred callouts)
    .replace(/^> (.+)$/gm, '<blockquote class="border-l-2 border-white/20 pl-4 text-gray-400 italic my-2">$1</blockquote>')
    // Bullet list items
    .replace(/^[-*] (.+)$/gm, '<li class="ml-4 text-gray-300 list-disc">$1</li>')
    // Numbered list items
    .replace(/^\d+\. (.+)$/gm, '<li class="ml-4 text-gray-300 list-decimal">$1</li>')
    // Wrap consecutive li in ul/ol
    .replace(/(<li[^>]*>[^<]*<\/li>\n?)+/g, (block) =>
      `<ul class="my-2 space-y-1">${block}</ul>`
    )
    // Simple table rows
    .replace(/^\|(.+)\|$/gm, (row) => {
      const cells = row
        .split("|")
        .slice(1, -1)
        .map((c) => c.trim());
      const isHeader = cells.every((c) => /^[-:]+$/.test(c));
      if (isHeader) return "";
      const tag = row.trim().startsWith("|---") ? "" : "td";
      const cellHtml = cells
        .map((c) => `<${tag || "td"} class="px-3 py-1.5 text-sm border-b border-white/10">${c}</${tag || "td"}>`)
        .join("");
      return `<tr>${cellHtml}</tr>`;
    })
    // Wrap table rows in table
    .replace(/(<tr>[\s\S]*?<\/tr>\n?)+/g, (block) =>
      `<div class="overflow-x-auto my-4"><table class="w-full border-collapse text-gray-300 text-sm">${block}</table></div>`
    )
    // Paragraphs (double newline → <p>)
    .replace(/\n\n([^<])/g, '</p><p class="text-gray-300 text-sm my-2">$1')
    // Line breaks
    .replace(/\n/g, "<br/>");

  return `<p class="text-gray-300 text-sm">${html}</p>`;
}

function escapeHtml(s: string) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function RESpec() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [session, setSession] = useState<ReverseEngineerSession | null>(null);
  const [activeSection, setActiveSection] = useState<RESectionId>("executive_summary");
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    getREStatus(id)
      .then(setSession)
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "Failed to load spec")
      );
  }, [id]);

  const handleDownload = async () => {
    if (!id) return;
    setDownloading(true);
    try {
      const blobUrl = await downloadRESpec(id);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = `spec_${session?.log_file_name?.replace(/\..+$/, "") ?? "re"}_${id?.slice(0, 8)}.zip`;
      a.click();
      URL.revokeObjectURL(blobUrl);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Download failed");
    } finally {
      setDownloading(false);
    }
  };

  if (!session && !error) {
    return (
      <div className="min-h-screen bg-[#0d1117] flex items-center justify-center">
        <div className="h-8 w-8 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />
      </div>
    );
  }

  const currentSection: SpecSection | undefined =
    session?.spec_sections?.[activeSection];

  const availableSections = new Set(session?.available_sections ?? []);

  // Overall confidence from confidence_report section
  const confReport = session?.spec_sections?.["confidence_report"];
  const overallConf = confReport?.confidence_score ?? 0;
  const totalGaps = Object.values(session?.spec_sections ?? {}).reduce(
    (sum, s) => sum + s.gap_count, 0
  );

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

        <div className="ml-auto">
          <button
            onClick={handleDownload}
            disabled={downloading || !session?.spec_section_count}
            className="flex items-center gap-2 px-4 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-400 text-white text-sm font-medium transition-colors"
          >
            {downloading ? (
              <span className="h-3 w-3 rounded-full border-2 border-white/30 border-t-white animate-spin" />
            ) : (
              "⬇ Download ZIP"
            )}
          </button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Left sidebar — section tabs */}
        <aside className="w-56 border-r border-white/10 flex flex-col overflow-y-auto">
          {/* Stats */}
          <div className="p-4 border-b border-white/10 space-y-2">
            <div className="text-xs text-gray-500 uppercase tracking-wider">Confidence</div>
            <div className="flex items-center gap-2">
              <div className="flex-1 h-2 rounded-full bg-white/10 overflow-hidden">
                <div
                  className="h-full bg-emerald-500 rounded-full"
                  style={{ width: `${overallConf * 100}%` }}
                />
              </div>
              <span className="text-sm font-semibold text-emerald-300">
                {Math.round(overallConf * 100)}%
              </span>
            </div>
            <div className="text-xs text-gray-500">
              {totalGaps} gap{totalGaps !== 1 ? "s" : ""} identified
            </div>
          </div>

          {/* Section list */}
          <nav className="flex-1 p-2 space-y-0.5">
            {RE_SECTION_IDS.map((sid) => {
              const meta = SECTION_META[sid];
              const available = availableSections.has(sid);
              const active = activeSection === sid;
              const section = session?.spec_sections?.[sid];

              return (
                <button
                  key={sid}
                  onClick={() => available && setActiveSection(sid)}
                  disabled={!available}
                  className={`
                    w-full text-left rounded-lg px-3 py-2 text-sm transition-colors flex items-center gap-2
                    ${active
                      ? "bg-blue-600/20 text-blue-300 border border-blue-600/30"
                      : available
                      ? "text-gray-300 hover:bg-white/5"
                      : "text-gray-600 cursor-not-allowed"
                    }
                  `}
                >
                  <span>{meta?.icon ?? "📄"}</span>
                  <span className="flex-1 truncate">{meta?.title ?? sid}</span>
                  {section && section.gap_count > 0 && (
                    <span className="text-[10px] text-red-400 font-mono">
                      {section.gap_count}g
                    </span>
                  )}
                  {!available && (
                    <span className="text-[10px] text-gray-600">…</span>
                  )}
                </button>
              );
            })}
          </nav>
        </aside>

        {/* Main content */}
        <main className="flex-1 overflow-y-auto p-6">
          {error && (
            <div className="rounded-xl bg-red-950/50 border border-red-500/30 px-5 py-4 text-red-300 text-sm">
              {error}
            </div>
          )}

          {currentSection ? (
            <motion.div
              key={activeSection}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-4"
            >
              {/* Section header */}
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h1 className="text-xl font-bold text-white">
                    {SECTION_META[activeSection]?.icon} {currentSection.title}
                  </h1>
                  <div className="flex items-center gap-3 mt-1">
                    <ConfidenceBadge
                      confidence={
                        currentSection.confidence_score > 0.7
                          ? "CONFIRMED"
                          : currentSection.confidence_score > 0.4
                          ? "INFERRED"
                          : "GAP"
                      }
                    />
                    <span className="text-xs text-gray-400">
                      {Math.round(currentSection.confidence_score * 100)}% grounded
                    </span>
                    {currentSection.gap_count > 0 && (
                      <span className="text-xs text-red-400">
                        {currentSection.gap_count} gap{currentSection.gap_count !== 1 ? "s" : ""}
                      </span>
                    )}
                  </div>
                </div>
              </div>

              {/* Markdown content */}
              <div
                className="prose prose-invert max-w-none"
                dangerouslySetInnerHTML={{
                  __html: renderMarkdown(currentSection.content_md),
                }}
              />
            </motion.div>
          ) : (
            <div className="flex flex-col items-center justify-center h-full gap-3 text-gray-600">
              <span className="text-4xl">📝</span>
              <p>Select a section from the sidebar</p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
