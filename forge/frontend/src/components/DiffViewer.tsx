import { useMemo } from "react";
import { FileCode, Plus, Minus, ChevronDown, ChevronRight } from "lucide-react";
import { motion } from "framer-motion";

interface DiffViewerProps {
  file: string;
  diff: string;
  expanded?: boolean;
  onToggle?: () => void;
  status?: "success" | "error" | "pending";
}

interface DiffLine {
  type: "add" | "remove" | "context" | "header" | "hunk";
  content: string;
  lineNumber?: { old?: number; new?: number };
}

function parseDiff(diff: string): DiffLine[] {
  const lines: DiffLine[] = [];
  let oldLine = 0;
  let newLine = 0;

  for (const line of diff.split("\n")) {
    if (line.startsWith("---") || line.startsWith("+++")) {
      lines.push({ type: "header", content: line });
    } else if (line.startsWith("@@")) {
      // Parse hunk header: @@ -start,count +start,count @@
      const match = line.match(/@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
      if (match) {
        oldLine = parseInt(match[1], 10);
        newLine = parseInt(match[2], 10);
      }
      lines.push({ type: "hunk", content: line });
    } else if (line.startsWith("+")) {
      lines.push({
        type: "add",
        content: line.slice(1),
        lineNumber: { new: newLine++ },
      });
    } else if (line.startsWith("-")) {
      lines.push({
        type: "remove",
        content: line.slice(1),
        lineNumber: { old: oldLine++ },
      });
    } else if (line.startsWith(" ") || line === "") {
      lines.push({
        type: "context",
        content: line.slice(1) || "",
        lineNumber: { old: oldLine++, new: newLine++ },
      });
    }
  }

  return lines;
}

export function DiffViewer({
  file,
  diff,
  expanded = true,
  onToggle,
  status = "success",
}: DiffViewerProps) {
  const parsedLines = useMemo(() => parseDiff(diff), [diff]);

  const stats = useMemo(() => {
    let additions = 0;
    let deletions = 0;
    for (const line of parsedLines) {
      if (line.type === "add") additions++;
      if (line.type === "remove") deletions++;
    }
    return { additions, deletions };
  }, [parsedLines]);

  const statusColor =
    status === "success"
      ? "var(--color-success)"
      : status === "error"
      ? "var(--color-error)"
      : "var(--color-warning)";

  return (
    <div className="rounded-lg border border-[var(--color-glass-border)] overflow-hidden bg-[var(--color-bg-primary)]">
      {/* File Header */}
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-3 px-4 py-3 bg-[var(--color-bg-elevated)] hover:bg-[var(--color-bg-hover)] transition-colors text-left"
      >
        {onToggle && (
          expanded ? (
            <ChevronDown size={16} className="text-[var(--color-text-muted)]" />
          ) : (
            <ChevronRight size={16} className="text-[var(--color-text-muted)]" />
          )
        )}
        
        <FileCode size={16} style={{ color: statusColor }} />
        
        <span className="flex-1 font-mono text-sm text-[var(--color-text-primary)] truncate">
          {file}
        </span>

        <div className="flex items-center gap-3 text-xs">
          <span className="flex items-center gap-1 text-[var(--color-success)]">
            <Plus size={12} />
            {stats.additions}
          </span>
          <span className="flex items-center gap-1 text-[var(--color-error)]">
            <Minus size={12} />
            {stats.deletions}
          </span>
        </div>
      </button>

      {/* Diff Content */}
      {expanded && (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: "auto", opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          className="overflow-x-auto"
        >
          <table className="w-full text-xs font-mono">
            <tbody>
              {parsedLines.map((line, i) => (
                <DiffLineRow key={i} line={line} />
              ))}
            </tbody>
          </table>
        </motion.div>
      )}
    </div>
  );
}

function DiffLineRow({ line }: { line: DiffLine }) {
  const bgColor =
    line.type === "add"
      ? "rgba(var(--color-success-rgb), 0.1)"
      : line.type === "remove"
      ? "rgba(var(--color-error-rgb), 0.1)"
      : line.type === "hunk"
      ? "var(--color-bg-elevated)"
      : "transparent";

  const textColor =
    line.type === "add"
      ? "var(--color-success)"
      : line.type === "remove"
      ? "var(--color-error)"
      : line.type === "header" || line.type === "hunk"
      ? "var(--color-text-muted)"
      : "var(--color-text-secondary)";

  const prefix =
    line.type === "add" ? "+" : line.type === "remove" ? "-" : " ";

  if (line.type === "header" || line.type === "hunk") {
    return (
      <tr style={{ backgroundColor: bgColor }}>
        <td
          colSpan={3}
          className="px-4 py-1"
          style={{ color: textColor }}
        >
          {line.content}
        </td>
      </tr>
    );
  }

  return (
    <tr style={{ backgroundColor: bgColor }}>
      {/* Old line number */}
      <td className="w-12 px-2 py-0.5 text-right text-[var(--color-text-dim)] select-none border-r border-[var(--color-glass-border)]">
        {line.lineNumber?.old ?? ""}
      </td>
      {/* New line number */}
      <td className="w-12 px-2 py-0.5 text-right text-[var(--color-text-dim)] select-none border-r border-[var(--color-glass-border)]">
        {line.lineNumber?.new ?? ""}
      </td>
      {/* Content */}
      <td className="px-4 py-0.5 whitespace-pre" style={{ color: textColor }}>
        <span className="select-none mr-2">{prefix}</span>
        {line.content}
      </td>
    </tr>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   Multi-file diff viewer
   ═══════════════════════════════════════════════════════════════════════════ */

interface DiffListProps {
  diffs: Array<{
    file: string;
    diff: string;
    status?: "success" | "error" | "pending";
  }>;
}

export function DiffList({ diffs }: DiffListProps) {
  return (
    <div className="space-y-4">
      {diffs.map((d, i) => (
        <motion.div
          key={d.file}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.05 }}
        >
          <DiffViewer
            file={d.file}
            diff={d.diff}
            status={d.status}
          />
        </motion.div>
      ))}
    </div>
  );
}

export default DiffViewer;
