// Data-driven Cytoscape styling, element mapping, and layouts.
//
// VISUAL TARGET (design plan): a clean light canvas with vibrant solid circular
// nodes, thin curved relationships that carry their type as an on-line caption
// for inferred edges, and LIVE cola physics so the graph gently drifts and
// reacts when you drag a node (the "molecule" feel).
//
// All colors/sizes here mirror the CSS custom properties in index.css so the
// graph and the surrounding chrome share one token system.

import type cytoscape from "cytoscape";
import type { ElementDefinition, LayoutOptions } from "cytoscape";
import type { GraphEdge, GraphNode } from "../types";
import { isServiceEdge } from "../types";

type Stylesheet = cytoscape.StylesheetStyle;

// --- per-level node styling (single source of truth) ------------------------

export interface LevelStyle {
  fill: string;
  ring: string;
  /** Label text color. Amber(file)/topic use dark text for contrast. */
  text: string;
  /** Circle diameter in px. */
  size: number;
  /** Ring (border) width in px. */
  ring_width: number;
  /** Label font size in px. */
  fontSize: number;
  /** Font weight for the label. */
  fontWeight: number;
  /** Max characters before truncating with an ellipsis. */
  maxChars: number;
  /** Whether the label is hidden until hover/select (identifier only). */
  labelHiddenByDefault?: boolean;
}

// Exact plan values: diameter / ring / label size + truncation length.
export const LEVEL_STYLES: Record<string, LevelStyle> = {
  service: {
    fill: "#5b8dff",
    ring: "#2f5fd9",
    text: "#ffffff",
    size: 100,        // LARGER for readable labels
    ring_width: 4,
    fontSize: 13,     // Bigger font
    fontWeight: 600,
    maxChars: 18,     // More characters visible
  },
  topic: {
    fill: "#b15bff",
    ring: "#8a2fe0",
    text: "#ffffff",
    size: 80,
    ring_width: 3,
    fontSize: 12,
    fontWeight: 600,
    maxChars: 16,
  },
  route: {
    fill: "#22b8b0",
    ring: "#0d8f88",
    text: "#ffffff",
    size: 70,
    ring_width: 3,
    fontSize: 11,
    fontWeight: 500,
    maxChars: 14,
  },
  file: {
    fill: "#ffb240",
    ring: "#e08b00",
    text: "#0b0f17",
    size: 60,
    ring_width: 2,
    fontSize: 11,
    fontWeight: 500,
    maxChars: 12,
  },
  function: {
    fill: "#4cc97c",
    ring: "#2fa35b",
    text: "#ffffff",
    size: 50,
    ring_width: 2,
    fontSize: 10,
    fontWeight: 500,
    maxChars: 10,
  },
  identifier: {
    fill: "#ff6f91",
    ring: "#e14169",
    text: "#ffffff",
    size: 40,
    ring_width: 2,
    fontSize: 10,
    fontWeight: 500,
    maxChars: 10,
    labelHiddenByDefault: true,
  },
} as const;

const DEFAULT_LEVEL: LevelStyle = LEVEL_STYLES.identifier;

function levelStyle(level: string): LevelStyle {
  return LEVEL_STYLES[level] ?? DEFAULT_LEVEL;
}

// Canvas + edge + animation colors, mirroring the CSS tokens.
export const COLORS = {
  bg: "#f7f8fa",
  edgeExact: "#b7bec9",
  edgeInferred: "#8b93a6",
  edgeCaptionBg: "#ffffff",
  edgeCaptionText: "#5b6472",
  blastTrail: "#ff5d3a",
  selectionGlow: "rgba(91, 141, 255, 0.35)",
} as const;

export const LEVEL_COLORS: Record<string, string> = Object.fromEntries(
  Object.entries(LEVEL_STYLES).map(([lvl, s]) => [lvl, s.fill]),
);

// --- element mapping (DTO -> cytoscape) --------------------------------------

/** Truncate a label so it fits inside the circle instead of overflowing. */
function shortLabel(label: string, level: string): string {
  const { maxChars } = levelStyle(level);
  if (label.length <= maxChars) return label;
  return label.slice(0, Math.max(1, maxChars - 1)) + "…";
}

export function nodeElement(node: GraphNode): ElementDefinition {
  return {
    group: "nodes",
    data: {
      id: node.id,
      label: shortLabel(node.label, node.level),
      fullLabel: node.label,
      level: node.level,
      repoId: node.repoId ?? null,
      hasChildren: node.hasChildren,
      expanded: false,
    },
    classes: `lvl-${node.level}`,
  };
}

export function edgeElement(edge: GraphEdge): ElementDefinition {
  const service = isServiceEdge(edge);
  // Inferred edges ALWAYS show a caption ("HTTP_CALLS · 92%"); exact edges show
  // their kind only on hover/select (kept in a data field, surfaced via style).
  const caption =
    service && edge.confidence !== null && edge.confidence !== undefined
      ? `${edge.kind} · ${Math.round(edge.confidence * 100)}%`
      : edge.kind;
  return {
    group: "edges",
    data: {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      kind: edge.kind,
      confidence: edge.confidence ?? null,
      lineColor: service ? COLORS.edgeInferred : COLORS.edgeExact,
      caption,
      // Inferred edges surface the caption at all times; exact edges leave it
      // blank until hovered/selected (handled by the .edge-code.hl rule).
      label: service ? caption : "",
    },
    classes: service ? "edge-service" : "edge-code",
  };
}

// --- stylesheet --------------------------------------------------------------

function levelNodeRules(): Stylesheet[] {
  const rules: Stylesheet[] = [];
  for (const [level, s] of Object.entries(LEVEL_STYLES)) {
    rules.push({
      selector: `node.lvl-${level}`,
      style: {
        width: s.size,
        height: s.size,
        "background-color": s.fill,
        "border-color": s.ring,
        "border-width": s.ring_width,
        color: s.text,
        "font-size": s.fontSize,
        "font-weight": s.fontWeight,
        // Keep labels inside the circle: diameter minus ~8px.
        "text-max-width": `${Math.max(16, s.size - 8)}px`,
      } as cytoscape.Css.Node,
    });
  }
  return rules;
}

export function stylesheet(): Stylesheet[] {
  return [
    // Base node: flat fill, ring stroke, NO drop shadow / NO background halo.
    // overlay-opacity:0 fixes the prior "square halo" bug.
    {
      selector: "node",
      style: {
        shape: "ellipse",
        label: "data(label)",
        "font-family": "Inter, system-ui, sans-serif",
        "font-size": 11,
        "font-weight": 500,
        "text-valign": "center",
        "text-halign": "center",
        "text-wrap": "ellipsis",
        "text-max-width": "48px",
        color: DEFAULT_LEVEL.text,
        width: DEFAULT_LEVEL.size,
        height: DEFAULT_LEVEL.size,
        "background-color": DEFAULT_LEVEL.fill,
        "border-width": DEFAULT_LEVEL.ring_width,
        "border-color": DEFAULT_LEVEL.ring,
        "overlay-opacity": 0,
        "transition-property": "border-width, width, height",
        "transition-duration": 120,
        "transition-timing-function": "ease-out",
      } as cytoscape.Css.Node,
    },
    ...levelNodeRules(),

    // Identifier labels are hidden until hover/select to reduce clutter.
    {
      selector: "node.lvl-identifier",
      style: { label: "" } as cytoscape.Css.Node,
    },

    // Expanded parent gets a subtle chevron-style badge via a darker ring tint
    // (represented as a slightly thicker ring, drawn on top).
    {
      selector: "node[?expanded]",
      style: {
        "border-style": "double",
      } as cytoscape.Css.Node,
    },

    // Hover: ONLY the hovered node changes (ring +2px, scale ~1.04). No dimming
    // of anything else in the graph.
    {
      selector: "node.hover",
      style: {
        "border-width": (ele: cytoscape.NodeSingular) =>
          levelStyle(String(ele.data("level"))).ring_width + 2,
        width: (ele: cytoscape.NodeSingular) =>
          levelStyle(String(ele.data("level"))).size * 1.04,
        height: (ele: cytoscape.NodeSingular) =>
          levelStyle(String(ele.data("level"))).size * 1.04,
        label: "data(label)",
        "z-index": 900,
      } as cytoscape.Css.Node,
    },

    // Selection: persistent outer glow ring via an overlay (kept subtle, no
    // square halo — overlay is a soft accent).
    {
      selector: "node:selected",
      style: {
        "border-width": (ele: cytoscape.NodeSingular) =>
          levelStyle(String(ele.data("level"))).ring_width + 2,
        "overlay-color": "#5b8dff",
        "overlay-opacity": 0.18,
        "overlay-padding": 8,
        label: "data(label)",
        "z-index": 950,
      } as cytoscape.Css.Node,
    },

    // Base edge: thin, gently curved, neutral, small arrowhead.
    {
      selector: "edge",
      style: {
        width: 1,
        "line-color": "data(lineColor)",
        "target-arrow-color": "data(lineColor)",
        "target-arrow-shape": "triangle",
        "arrow-scale": 0.7,
        "curve-style": "unbundled-bezier",
        "control-point-distances": [20],
        "control-point-weights": [0.5],
        label: "data(label)",
        "font-family": "Inter, system-ui, sans-serif",
        "font-size": 10,
        "font-weight": 500,
        color: COLORS.edgeCaptionText,
        "text-rotation": "autorotate",
        "text-background-color": COLORS.edgeCaptionBg,
        "text-background-opacity": 1,
        "text-background-shape": "roundrectangle",
        "text-background-padding": "3px",
        "text-border-color": "#e2e6ec",
        "text-border-width": 1,
        "text-border-opacity": 1,
        "min-zoomed-font-size": 7,
        "transition-property": "line-color, width",
        "transition-duration": 120,
      } as cytoscape.Css.Edge,
    },
    {
      selector: "edge.edge-code",
      style: { "line-style": "solid", width: 1 } as cytoscape.Css.Edge,
    },
    {
      selector: "edge.edge-service",
      style: {
        "line-style": "dashed",
        "line-dash-pattern": [4, 3],
        width: 1.5,
      } as cytoscape.Css.Edge,
    },
    // Exact edges show their caption only when highlighted (hover/select).
    {
      selector: "edge.edge-code.hl",
      style: { label: "data(caption)" } as cytoscape.Css.Edge,
    },
    // Hover: thicken connected edges +0.5px (no dimming elsewhere).
    {
      selector: "edge.hl",
      style: {
        width: (ele: cytoscape.EdgeSingular) =>
          (ele.hasClass("edge-service") ? 1.5 : 1) + 0.5,
        "z-index": 800,
      } as cytoscape.Css.Edge,
    },

    // --- Blast-radius animation state ----------------------------------------
    // Traversed edges light up in blast-trail and STAY lit.
    {
      selector: "edge.traversal",
      style: {
        "line-color": COLORS.blastTrail,
        "target-arrow-color": COLORS.blastTrail,
        width: (ele: cytoscape.EdgeSingular) =>
          (ele.hasClass("edge-service") ? 1.5 : 1) + 1,
        "line-style": "solid",
        "z-index": 999,
        label: "",
      } as cytoscape.Css.Edge,
    },
    // Arrived / impacted node: keep its category fill, ring becomes blast-trail
    // 3px with a persistent soft outer glow (overlay).
    {
      selector: "node.impacted",
      style: {
        "border-color": COLORS.blastTrail,
        "border-width": 3,
        "overlay-color": COLORS.blastTrail,
        "overlay-opacity": 0.22,
        "overlay-padding": 10,
        "z-index": 998,
      } as cytoscape.Css.Node,
    },
    // --- Persistent "what's affected" highlight (FIX 6) ----------------------
    // Every affected node keeps its category fill but gains a bold blast-color
    // ring and grows slightly, so the impacted subgraph stands out at a glance.
    {
      selector: "node.affected",
      style: {
        "border-color": COLORS.blastTrail,
        "border-width": (ele: cytoscape.NodeSingular) =>
          levelStyle(String(ele.data("level"))).ring_width + 2.5,
        width: (ele: cytoscape.NodeSingular) =>
          levelStyle(String(ele.data("level"))).size * 1.12,
        height: (ele: cytoscape.NodeSingular) =>
          levelStyle(String(ele.data("level"))).size * 1.12,
        "z-index": 990,
      } as cytoscape.Css.Node,
    },
    // Affected edges: blast-colored and thicker so the flow is obvious.
    {
      selector: "edge.affected",
      style: {
        "line-color": COLORS.blastTrail,
        "target-arrow-color": COLORS.blastTrail,
        width: (ele: cytoscape.EdgeSingular) =>
          (ele.hasClass("edge-service") ? 1.5 : 1) + 1.5,
        "z-index": 985,
      } as cytoscape.Css.Edge,
    },
    // Everything NOT affected is de-emphasized so the blast radius pops.
    {
      selector: "node.faded",
      style: { opacity: 0.15 } as cytoscape.Css.Node,
    },
    {
      selector: "edge.faded",
      style: { opacity: 0.15 } as cytoscape.Css.Edge,
    },

    // The travelling comet dot (a transient standalone node element).
    {
      selector: "node.blast-dot",
      style: {
        width: 12,
        height: 12,
        "background-color": COLORS.blastTrail,
        "border-width": 0,
        "overlay-color": COLORS.blastTrail,
        "overlay-opacity": 0.35,
        "overlay-padding": 8,
        label: "",
        events: "no",
        "z-index": 1000,
      } as cytoscape.Css.Node,
    },
    // Faint pulsing placeholder nodes shown while children are fetched.
    {
      selector: "node.placeholder",
      style: {
        width: 18,
        height: 18,
        "background-color": "#c7cdd8",
        "border-width": 0,
        opacity: 0.5,
        label: "",
        events: "no",
        "z-index": 1,
      } as cytoscape.Css.Node,
    },
  ];
}

// --- layouts -----------------------------------------------------------------

let colaAvailable = false;
export function setColaAvailable(v: boolean): void {
  colaAvailable = v;
}

let fcoseAvailable = false;
export function setFcoseAvailable(v: boolean): void {
  fcoseAvailable = v;
}

let dagreAvailable = false;
export function setDagreAvailable(v: boolean): void {
  dagreAvailable = v;
}

export function isColaAvailable(): boolean {
  return colaAvailable;
}

export function isDagreAvailable(): boolean {
  return dagreAvailable;
}

/**
 * Full-graph layout. Prefers `cola` for FORCE-DIRECTED layout that creates
 * Neo4j-style circular arrangement where children surround their parent.
 * Falls back to fcose, cose.
 *
 * @param incremental when true (expand/merge) keep positions stable so new
 *        nodes ease in near their parent instead of the whole graph reshuffling.
 */
export function fullLayout(incremental = false): LayoutOptions {
  // COLA: Force-directed physics layout - children surround parent naturally
  if (colaAvailable) {
    return {
      name: "cola",
      animate: true,
      infinite: false,  // Stop after convergence for performance
      fit: true,
      padding: 100,
      // Longer edge lengths for better separation and readability
      edgeLength: (edge: cytoscape.EdgeSingular) =>
        edge.hasClass("edge-service") ? 300 : 150,
      nodeSpacing: () => 100,
      // Lower gravity for looser circular layout
      gravity: 0.05,
      randomize: !incremental,
      handleDisconnected: true,
      avoidOverlap: true,
      // More iterations for better layout
      unconstrIter: 50,
      userConstIter: 60,
      allConstIter: 80,
    } as unknown as LayoutOptions;
  }
  if (fcoseAvailable) {
    return {
      name: "fcose",
      animate: true,
      animationDuration: 700,
      randomize: !incremental,
      fit: true,
      padding: 100,
      // Better separation parameters for circular layout
      nodeSeparation: 300,
      idealEdgeLength: (edge: cytoscape.EdgeSingular) =>
        edge.hasClass("edge-service") ? 300 : 150,
      nodeRepulsion: 25000,
      edgeElasticity: 0.45,
      nestingFactor: 0.1,
      gravity: 0.05,
      numIter: 3000,
      // Place disconnected components separately
      tile: true,
      tilingPaddingVertical: 80,
      tilingPaddingHorizontal: 80,
    } as unknown as LayoutOptions;
  }
  // DAGRE: Hierarchical layout - fallback option
  if (dagreAvailable) {
    return {
      name: "dagre",
      animate: true,
      animationDuration: 500,
      fit: true,
      padding: 80,
      rankDir: "TB",
      nodeSep: 150,
      rankSep: 200,
      edgeSep: 50,
      align: "UL",
      ranker: "network-simplex",
    } as unknown as LayoutOptions;
  }
  return {
    name: "cose",
    animate: true,
    animationDuration: 700,
    fit: true,
    padding: 100,
    nodeRepulsion: 1500000,
    nodeOverlap: 80,
    idealEdgeLength: 300,
    edgeElasticity: 100,
    nestingFactor: 5,
    gravity: 30,
    numIter: 2000,
    initialTemp: 200,
    coolingFactor: 0.95,
    minTemp: 1.0,
  } as unknown as LayoutOptions;
}
