import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import cytoscape, { type Core, type NodeSingular } from "cytoscape";
import fcose from "cytoscape-fcose";
import cola from "cytoscape-cola";
import dagre from "cytoscape-dagre";
import { Boxes } from "lucide-react";
import { expandNode, getGraphTop } from "../api";
import type { GraphNode, GraphView } from "../types";
import {
  edgeElement,
  fullLayout,
  isColaAvailable,
  nodeElement,
  setColaAvailable,
  setDagreAvailable,
  setFcoseAvailable,
  stylesheet,
} from "./cytoConfig";

// Register layout extensions once.
let extsRegistered = false;
function ensureExtensions(): void {
  if (extsRegistered) return;
  extsRegistered = true;
  // Register dagre FIRST (highest priority for hierarchical layout)
  try {
    cytoscape.use(dagre);
    setDagreAvailable(true);
  } catch {
    setDagreAvailable(false);
  }
  try {
    cytoscape.use(cola);
    setColaAvailable(true);
  } catch {
    setColaAvailable(false);
  }
  try {
    cytoscape.use(fcose);
    setFcoseAvailable(true);
  } catch {
    setFcoseAvailable(false);
  }
}

export interface GraphCanvasHandle {
  getCy(): Core | null;
  reload(): Promise<void>;
  mergeView(view: GraphView): string[];
  focusOnPath(nodeIds: string[]): void;
  expandNodeById(id: string): void;
  collapseNodeById(id: string): void;
  selectNodeById(id: string): void;
  fitAll(): void;
}

interface GraphCanvasProps {
  onSelectNode?: (node: GraphNode | null) => void;
  reloadSignal?: number;
  onError?: (message: string) => void;
}

const GraphCanvas = forwardRef<GraphCanvasHandle, GraphCanvasProps>(
  function GraphCanvas({ onSelectNode, reloadSignal, onError }, ref) {
    const containerRef = useRef<HTMLDivElement | null>(null);
    const cyRef = useRef<Core | null>(null);
    const layoutRef = useRef<cytoscape.Layouts | null>(null);
    const expandedRef = useRef<Set<string>>(new Set());
    // Track parent -> child ids so a collapse can remove exactly what it added.
    const childrenRef = useRef<Map<string, Set<string>>>(new Map());
    const [busy, setBusy] = useState(false);
    const [isEmpty, setIsEmpty] = useState(true);

    // Run continuous cola physics. `incremental` keeps existing positions so
    // new nodes ease in near their parent rather than the graph reshuffling.
    const runPhysics = useCallback((incremental = false) => {
      const cy = cyRef.current;
      if (!cy || cy.elements().empty()) return;
      layoutRef.current?.stop();
      const layout = cy.layout(fullLayout(incremental));
      layoutRef.current = layout;
      layout.run();
    }, []);

    const mergeView = useCallback((view: GraphView): string[] => {
      const cy = cyRef.current;
      if (!cy) return [];
      const addedIds: string[] = [];
      cy.batch(() => {
        for (const node of view.nodes) {
          if (cy.getElementById(node.id).empty()) {
            cy.add(nodeElement(node));
            addedIds.push(node.id);
          }
        }
        for (const edge of view.edges) {
          if (cy.getElementById(edge.id).empty()) {
            const hasEnds =
              cy.getElementById(edge.source).nonempty() &&
              cy.getElementById(edge.target).nonempty();
            if (hasEnds) cy.add(edgeElement(edge));
          }
        }
      });
      if (cy.elements().nonempty()) setIsEmpty(false);
      return addedIds;
    }, []);

    // Animate freshly added children outward from the parent position:
    // opacity 0->1, scale 0.3->1, 300ms, staggered 40ms.
    const spawnChildren = useCallback(
      (parentId: string, addedIds: string[]) => {
        const cy = cyRef.current;
        if (!cy) return;
        const parent = cy.getElementById(parentId);
        if (parent.empty()) return;
        const p = (parent as unknown as NodeSingular).position();
        addedIds.forEach((id, i) => {
          const n = cy.getElementById(id);
          if (n.empty() || !n.isNode()) return;
          const node = n as unknown as NodeSingular;
          const finalW = node.width();
          const finalH = node.height();
          // Start collapsed at the parent, invisible.
          node.position({ x: p.x, y: p.y });
          node.style({ opacity: 0, width: finalW * 0.3, height: finalH * 0.3 });
          setTimeout(() => {
            node.animate(
              { style: { opacity: 1, width: finalW, height: finalH } },
              { duration: 300, easing: "ease-out" },
            );
          }, i * 40);
        });
      },
      [],
    );

    const focusOnPath = useCallback((nodeIds: string[]) => {
      const cy = cyRef.current;
      if (!cy) return;
      const present = cy.collection();
      nodeIds.forEach((id) => {
        const n = cy.getElementById(id);
        if (n.nonempty()) present.merge(n);
      });
      if (present.nonempty()) {
        cy.animate({ fit: { eles: present, padding: 90 }, duration: 500 });
      }
    }, []);

    const fitAll = useCallback(() => {
      const cy = cyRef.current;
      if (!cy || cy.elements().empty()) return;
      cy.animate({ fit: { eles: cy.elements(), padding: 70 }, duration: 400 });
    }, []);

    const loadTop = useCallback(async () => {
      const cy = cyRef.current;
      if (!cy) return;
      setBusy(true);
      try {
        const view = await getGraphTop();
        layoutRef.current?.stop();
        cy.elements().remove();
        expandedRef.current.clear();
        childrenRef.current.clear();
        mergeView(view);
        setIsEmpty(cy.elements().empty());
        runPhysics(false);
        setTimeout(() => fitAll(), 450);
      } catch (err) {
        onError?.(err instanceof Error ? err.message : String(err));
      } finally {
        setBusy(false);
      }
    }, [mergeView, onError, runPhysics, fitAll]);

    // Show ~3 faint pulsing placeholder nodes near the parent while fetching.
    const showPlaceholders = useCallback((parentId: string): string[] => {
      const cy = cyRef.current;
      if (!cy) return [];
      const parent = cy.getElementById(parentId);
      if (parent.empty()) return [];
      const p = (parent as unknown as NodeSingular).position();
      const ids: string[] = [];
      for (let i = 0; i < 3; i += 1) {
        const id = `__ph_${parentId}_${i}_${Date.now()}`;
        const angle = (i / 3) * Math.PI * 2;
        cy.add({
          group: "nodes",
          data: { id },
          classes: "placeholder",
          position: { x: p.x + Math.cos(angle) * 44, y: p.y + Math.sin(angle) * 44 },
          selectable: false,
          grabbable: false,
        });
        const ph = cy.getElementById(id);
        // 600ms shimmer loop.
        const shimmer = () => {
          if (cy.getElementById(id).empty()) return;
          ph.animate(
            { style: { opacity: 0.15 } },
            {
              duration: 300,
              complete: () => {
                if (cy.getElementById(id).empty()) return;
                ph.animate({ style: { opacity: 0.5 } }, { duration: 300, complete: shimmer });
              },
            },
          );
        };
        shimmer();
        ids.push(id);
      }
      return ids;
    }, []);

    // Open a node in place: pulse to confirm click, show placeholders while the
    // fetch is in flight, then spawn the children outward.
    const doExpand = useCallback(
      async (node: NodeSingular) => {
        const cy = cyRef.current;
        if (!cy) return;
        const id = node.id();
        if (!node.data("hasChildren") || expandedRef.current.has(id)) return;
        expandedRef.current.add(id);
        node.data("expanded", true);

        // Confirm-click pulse: ring scale 1.0 -> 1.3 -> 1.0 over 250ms.
        const baseW = node.width();
        const baseH = node.height();
        node.animate(
          { style: { width: baseW * 1.3, height: baseH * 1.3 } },
          {
            duration: 125,
            complete: () => {
              node.animate(
                { style: { width: baseW, height: baseH } },
                { duration: 125 },
              );
            },
          },
        );

        const placeholders = showPlaceholders(id);
        setBusy(true);
        try {
          const view = await expandNode(id);
          placeholders.forEach((phId) => cy.getElementById(phId).remove());
          const added = mergeView(view);
          // Record children of THIS parent (nodes newly added by this expand).
          const kids = new Set(added.filter((a) => a !== id));
          childrenRef.current.set(id, kids);
          spawnChildren(id, [...kids]);
          runPhysics(true);
        } catch (err) {
          placeholders.forEach((phId) => cy.getElementById(phId).remove());
          expandedRef.current.delete(id);
          node.data("expanded", false);
          onError?.(err instanceof Error ? err.message : String(err));
        } finally {
          setBusy(false);
        }
      },
      [mergeView, onError, runPhysics, showPlaceholders, spawnChildren],
    );

    // Collapse: reverse animation (200ms fade + scale down) then remove the
    // children this parent added.
    const doCollapse = useCallback(
      (parentId: string) => {
        const cy = cyRef.current;
        if (!cy) return;
        const parent = cy.getElementById(parentId);
        if (parent.empty()) return;
        const kids = childrenRef.current.get(parentId);
        parent.data("expanded", false);
        expandedRef.current.delete(parentId);
        childrenRef.current.delete(parentId);
        if (!kids || kids.size === 0) return;
        const p = (parent as unknown as NodeSingular).position();
        kids.forEach((kidId) => {
          // Collapse descendants recursively so nested opens clean up too.
          if (expandedRef.current.has(kidId)) doCollapse(kidId);
          const kid = cy.getElementById(kidId);
          if (kid.empty()) return;
          const kn = kid as unknown as NodeSingular;
          kn.animate(
            { position: { x: p.x, y: p.y }, style: { opacity: 0 } },
            {
              duration: 200,
              easing: "ease-in",
              complete: () => {
                if (cy.getElementById(kidId).nonempty()) cy.getElementById(kidId).remove();
              },
            },
          );
        });
        setTimeout(() => runPhysics(true), 220);
      },
      [runPhysics],
    );

    useEffect(() => {
      ensureExtensions();
      if (!containerRef.current || cyRef.current) return;
      const cy = cytoscape({
        container: containerRef.current,
        elements: [],
        style: stylesheet(),
        minZoom: 0.15,
        maxZoom: 2.5,
        wheelSensitivity: 0.25,
      });
      cyRef.current = cy;

      // Single click: select (details) AND open the node's internals lazily.
      cy.on("tap", "node", (evt) => {
        const node = evt.target as NodeSingular;
        if (node.hasClass("placeholder") || node.hasClass("blast-dot")) return;
        onSelectNode?.({
          id: node.id(),
          label: node.data("fullLabel") ?? node.data("label"),
          level: node.data("level"),
          repoId: node.data("repoId"),
          hasChildren: !!node.data("hasChildren"),
        });
        if (node.data("hasChildren") && !expandedRef.current.has(node.id())) {
          void doExpand(node);
        }
      });

      // Click empty space clears selection (details auto-dismiss).
      cy.on("tap", (evt) => {
        if (evt.target === cy) onSelectNode?.(null);
      });

      // Hover: ONLY the hovered node + its connected edges change. No dimming.
      cy.on("mouseover", "node", (evt) => {
        const node = evt.target as NodeSingular;
        if (node.hasClass("placeholder") || node.hasClass("blast-dot")) return;
        node.addClass("hover");
        node.connectedEdges().addClass("hl");
        const c = cy.container();
        if (c) c.style.cursor = "pointer";
      });
      cy.on("mouseout", "node", (evt) => {
        const node = evt.target as NodeSingular;
        node.removeClass("hover");
        node.connectedEdges().removeClass("hl");
        const c = cy.container();
        if (c) c.style.cursor = "default";
      });

      // Drag pins a node and perturbs neighbors (molecule feel); dbl-click
      // unpins so cola can move it again.
      cy.on("grab", "node", (evt) => {
        (evt.target as NodeSingular).lock();
        if (isColaAvailable()) runPhysics(true);
      });
      cy.on("dbltap", "node", (evt) => {
        const node = evt.target as NodeSingular;
        node.unlock();
        if (isColaAvailable()) runPhysics(true);
      });

      void loadTop();

      return () => {
        layoutRef.current?.stop();
        cy.destroy();
        cyRef.current = null;
      };
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    useEffect(() => {
      if (reloadSignal === undefined) return;
      void loadTop();
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [reloadSignal]);

    useImperativeHandle(
      ref,
      () => ({
        getCy: () => cyRef.current,
        reload: loadTop,
        mergeView: (view: GraphView): string[] => {
          const added = mergeView(view);
          if (added.length > 0) runPhysics(true);
          return added;
        },
        focusOnPath,
        expandNodeById: (id: string) => {
          const cy = cyRef.current;
          if (!cy) return;
          const n = cy.getElementById(id);
          if (n.nonempty() && n.isNode()) void doExpand(n as unknown as NodeSingular);
        },
        collapseNodeById: (id: string) => doCollapse(id),
        selectNodeById: (id: string) => {
          const cy = cyRef.current;
          if (!cy) return;
          const n = cy.getElementById(id);
          if (n.nonempty()) {
            cy.nodes().unselect();
            n.select();
          }
        },
        fitAll,
      }),
      [loadTop, mergeView, focusOnPath, runPhysics, doExpand, doCollapse, fitAll],
    );

    return (
      <div className="graph-canvas-wrap">
        <div ref={containerRef} className="graph-canvas" />
        {isEmpty && !busy && (
          <div className="canvas-empty">
            <Boxes className="canvas-empty-icon" size={72} strokeWidth={1.2} />
            <h2>Build your network graph</h2>
            <p>
              Ingest a repository to map services, files, and cross-service
              calls. Click a node to open it and see inside.
            </p>
          </div>
        )}
        {busy && (
          <div className="canvas-badge" role="status">
            <span className="spinner spinner-sm" /> working…
          </div>
        )}
      </div>
    );
  },
);

export default GraphCanvas;
