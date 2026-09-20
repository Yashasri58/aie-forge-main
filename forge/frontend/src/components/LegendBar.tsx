import { useEffect, useState, type RefObject } from "react";
import type { GraphCanvasHandle } from "../graph/GraphCanvas";
import { LEVEL_STYLES } from "../graph/cytoConfig";

// Persistent floating legend, bottom-left: a swatch + label + count per node
// level PRESENT in the current view, a divider, then edge legend (solid Exact /
// dashed Inferred %). Counts update live as nodes expand/collapse.

const LEVEL_ORDER: { level: string; label: string }[] = [
  { level: "service", label: "Service" },
  { level: "topic", label: "Topic" },
  { level: "route", label: "Route" },
  { level: "file", label: "File" },
  { level: "function", label: "Function" },
  { level: "identifier", label: "Identifier" },
];

interface Counts {
  nodes: Record<string, number>;
  hasServiceEdges: boolean;
  hasCodeEdges: boolean;
}

const EMPTY: Counts = { nodes: {}, hasServiceEdges: false, hasCodeEdges: false };

export default function LegendBar({
  canvasRef,
}: {
  canvasRef: RefObject<GraphCanvasHandle | null>;
}) {
  const [counts, setCounts] = useState<Counts>(EMPTY);

  // Poll the live graph so the legend tracks ingest/expand/collapse/GRACE
  // merges without threading events through every mutation path.
  useEffect(() => {
    let stop = false;
    let timer = 0;
    const tick = () => {
      if (stop) return;
      const cy = canvasRef.current?.getCy() ?? null;
      if (cy) {
        const nodes: Record<string, number> = {};
        cy.nodes().forEach((n) => {
          if (n.hasClass("placeholder") || n.hasClass("blast-dot")) return;
          const lvl = String(n.data("level") ?? "identifier");
          nodes[lvl] = (nodes[lvl] ?? 0) + 1;
        });
        const hasServiceEdges = cy.edges(".edge-service").nonempty();
        const hasCodeEdges = cy.edges(".edge-code").nonempty();
        setCounts((prev) => {
          const same =
            prev.hasServiceEdges === hasServiceEdges &&
            prev.hasCodeEdges === hasCodeEdges &&
            JSON.stringify(prev.nodes) === JSON.stringify(nodes);
          return same ? prev : { nodes, hasServiceEdges, hasCodeEdges };
        });
      }
      timer = window.setTimeout(tick, 700);
    };
    tick();
    return () => {
      stop = true;
      window.clearTimeout(timer);
    };
  }, [canvasRef]);

  const present = LEVEL_ORDER.filter((l) => (counts.nodes[l.level] ?? 0) > 0);
  if (present.length === 0) return null;

  return (
    <div className="legend" role="group" aria-label="Graph legend">
      <div className="legend-items">
        {present.map(({ level, label }) => {
          const s = LEVEL_STYLES[level];
          return (
            <span key={level} className="legend-item" title={`${label}: ${counts.nodes[level]}`}>
              <span
                className="legend-swatch"
                style={{ backgroundColor: s.fill, borderColor: s.ring }}
              />
              {label}
              <span className="legend-count">{counts.nodes[level]}</span>
            </span>
          );
        })}
      </div>

      {(counts.hasCodeEdges || counts.hasServiceEdges) && (
        <>
          <span className="legend-divider" />
          <div className="legend-edges">
            {counts.hasCodeEdges && (
              <span className="legend-edge" title="Exact code relationships">
                <span className="legend-edge-line exact" />
                Exact
              </span>
            )}
            {counts.hasServiceEdges && (
              <span
                className="legend-edge"
                title="Inferred cross-service relationships (caption shows confidence)"
              >
                <span className="legend-edge-line inferred" />
                Inferred %
              </span>
            )}
          </div>
        </>
      )}
    </div>
  );
}
