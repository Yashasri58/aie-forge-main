import type { GraphNode } from "../types";
import { LEVEL_STYLES } from "../graph/cytoConfig";

interface DetailsPanelProps {
  node: GraphNode;
  expanded: boolean;
  onExpand: () => void;
  onCollapse: () => void;
  onFocus: () => void;
}

// A node's metadata rows + footer actions. Rendered inside the right drawer
// only when a node is selected (the drawer itself handles show/hide).
export default function DetailsPanel({
  node,
  expanded,
  onExpand,
  onCollapse,
  onFocus,
}: DetailsPanelProps) {
  const style = LEVEL_STYLES[node.level] ?? LEVEL_STYLES.identifier;

  // File path: for file/identifier/function levels the label often encodes a
  // path. Surface it in monospace when it looks path-like.
  const looksLikePath = /[\\/]/.test(node.label) || node.label.includes("::");

  return (
    <>
      <div className="detail-rows">
        <div className="detail-row">
          <span className="detail-row-label">Type</span>
          <span
            className="level-badge"
            style={{ color: style.fill, borderColor: style.ring }}
          >
            {node.level}
          </span>
        </div>

        {node.repoId && (
          <div className="detail-row">
            <span className="detail-row-label">Owning service</span>
            <span className="detail-row-value mono">{node.repoId}</span>
          </div>
        )}

        {looksLikePath && (
          <div className="detail-row">
            <span className="detail-row-label">File path</span>
            <span className="detail-row-value mono">{node.label}</span>
          </div>
        )}

        <div className="detail-row">
          <span className="detail-row-label">Node id</span>
          <span className="detail-row-value mono" style={{ fontSize: 12 }}>
            {node.id}
          </span>
        </div>

        <div className="detail-row">
          <span className="detail-row-label">Children</span>
          <span className="detail-row-value">
            {node.hasChildren ? "Has children" : "None"}
          </span>
        </div>
      </div>

      <div className="detail-actions">
        {node.hasChildren &&
          (expanded ? (
            <button className="btn-secondary" onClick={onCollapse}>
              Collapse children
            </button>
          ) : (
            <button className="btn-secondary" onClick={onExpand}>
              Expand children
            </button>
          ))}
        <button className="btn-secondary" onClick={onFocus}>
          Focus in graph
        </button>
      </div>
    </>
  );
}
