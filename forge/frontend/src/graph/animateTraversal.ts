// Client-side blast-radius animation (the centerpiece).
//
// Given the ordered `traversal_path` from a GRACE query, a glowing 12px dot in
// blast-trail #FF5D3A travels edge-by-edge along the path (~180ms per hop). As
// it passes, the traversed edge lights up and STAYS lit, and the arrived node
// flashes then settles into a highlighted "impacted" state (category fill kept,
// ring becomes blast-trail with a persistent soft outer glow). After the trail,
// all impacted nodes pulse once in unison as a "landed" beat.
//
// NON-impacted elements are never dimmed — impacted state is conveyed purely by
// glow/highlight. Everything is client-side; callers must merge the GRACE
// subgraph onto the canvas first so there are real elements to light up.

import type { Core, EdgeCollection, NodeSingular } from "cytoscape";

/** Handle so a new query can cancel a running trail. */
export interface TraversalAnimation {
  cancel(): void;
  done: Promise<void>;
}

const HOP_MS = 180; // per-hop travel time
const MAX_TOTAL_MS = 2500; // compress if path is long
const FLASH_MS = 160;
const LANDED_MS = 200;

/** Find an edge connecting two node ids, in either direction. */
function edgeBetween(cy: Core, a: string, b: string): EdgeCollection {
  const forward = cy.edges(
    `[source = "${escapeAttr(a)}"][target = "${escapeAttr(b)}"]`,
  );
  if (forward.nonempty()) return forward;
  return cy.edges(`[source = "${escapeAttr(b)}"][target = "${escapeAttr(a)}"]`);
}

function escapeAttr(id: string): string {
  return id.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}

/**
 * Race a glowing comet across the traversal path. Returns a handle whose
 * `done` promise resolves when the trail lands (or immediately on cancel).
 */
export function animateTraversal(cy: Core, path: string[]): TraversalAnimation {
  const timers: ReturnType<typeof setTimeout>[] = [];
  let cancelled = false;
  let resolveDone: () => void = () => {};
  const done = new Promise<void>((resolve) => {
    resolveDone = resolve;
  });

  const present = path.filter((id) => cy.getElementById(id).nonempty());
  if (present.length === 0) {
    resolveDone();
    return { cancel: () => {}, done };
  }

  // Compress per-hop timing so the whole reveal stays under the budget.
  const hops = Math.max(1, present.length - 1);
  const hopMs = Math.min(HOP_MS, MAX_TOTAL_MS / hops);

  // Create a transient comet dot node positioned at the first path node.
  const first = cy.getElementById(present[0]) as unknown as NodeSingular;
  const dot = cy.add({
    group: "nodes",
    data: { id: `__blast_dot_${Date.now()}` },
    classes: "blast-dot",
    position: { ...first.position() },
    selectable: false,
    grabbable: false,
  });

  const cleanupDot = () => {
    if (dot && dot.inside()) dot.remove();
  };

  const schedule = (fn: () => void, delay: number) => {
    const t = setTimeout(() => {
      if (!cancelled) fn();
    }, delay);
    timers.push(t);
  };

  let clock = 0;

  // Flash + settle the very first node.
  schedule(() => flashNode(cy, present[0]), clock);

  for (let i = 0; i + 1 < present.length; i += 1) {
    const from = present[i];
    const to = present[i + 1];
    const start = clock;
    clock += hopMs;

    // Travel the comet dot from `from` to `to` over this hop.
    schedule(() => {
      const target = cy.getElementById(to);
      if (target.nonempty() && dot.inside()) {
        dot.animate(
          { position: { ...(target as unknown as NodeSingular).position() } },
          { duration: hopMs, easing: "ease-in-out-sine" },
        );
      }
      // Light the traversed edge as the dot leaves — it stays lit.
      const edge = edgeBetween(cy, from, to);
      if (edge.nonempty()) edge.addClass("traversal");
    }, start);

    // On arrival, flash the destination node then settle to impacted.
    schedule(() => flashNode(cy, to), clock);
  }

  // After the trail: unison "landed" pulse of all impacted nodes.
  clock += FLASH_MS;
  schedule(() => {
    cleanupDot();
    landedPulse(cy, present);
  }, clock);

  clock += LANDED_MS + 60;
  schedule(() => resolveDone(), clock);

  return {
    cancel(): void {
      if (cancelled) return;
      cancelled = true;
      timers.forEach((t) => clearTimeout(t));
      timers.length = 0;
      cleanupDot();
      clearTraversal(cy);
      resolveDone();
    },
    done,
  };
}

/** Flash a node's ring in blast-trail, then settle to the persistent impacted state. */
function flashNode(cy: Core, id: string): void {
  const node = cy.getElementById(id);
  if (node.empty()) return;
  node.addClass("impacted");
  node.animate(
    { style: { "border-width": 6 } },
    {
      duration: FLASH_MS,
      complete: () => {
        node.animate({ style: { "border-width": 3 } }, { duration: FLASH_MS });
      },
    },
  );
}

/** One unison scale pulse (1 -> 1.08 -> 1) as the "landed" beat. */
function landedPulse(cy: Core, ids: string[]): void {
  ids.forEach((id) => {
    const node = cy.getElementById(id);
    if (node.empty()) return;
    const w = node.width();
    const h = node.height();
    node.animate(
      { style: { width: w * 1.08, height: h * 1.08 } },
      {
        duration: LANDED_MS / 2,
        complete: () => {
          node.animate(
            { style: { width: w, height: h } },
            { duration: LANDED_MS / 2 },
          );
        },
      },
    );
  });
}

/**
 * Ensure impacted services carry the highlighted state (in case they were not
 * on the traversal path itself). Called as the trail lands.
 */
export function highlightImpactedServices(cy: Core, serviceIds: string[]): void {
  serviceIds.forEach((id) => {
    const node = cy.getElementById(id);
    if (node.nonempty() && !node.hasClass("impacted")) {
      node.addClass("impacted");
    }
  });
}

/**
 * Persistent "what's affected" highlight (FIX 6). After the comet trail lands,
 * mark EVERY affected node/edge from the GRACE subgraph with `.affected` so the
 * whole blast radius reads at a glance, and de-emphasize everything else with
 * `.faded`. Impacted services additionally get the strongest `.impacted` ring.
 *
 * `nodeIds` / `edgeIds` are the ids from the GRACE result (res.nodes/res.edges);
 * `serviceIds` are the impacted services (highlighted strongest).
 */
export function highlightAffectedSubgraph(
  cy: Core,
  nodeIds: string[],
  edgeIds: string[],
  serviceIds: string[] = [],
): void {
  const affectedNodes = new Set(nodeIds);
  const affectedEdges = new Set(edgeIds);

  cy.batch(() => {
    cy.nodes().forEach((n) => {
      if (n.hasClass("blast-dot") || n.hasClass("placeholder")) return;
      if (affectedNodes.has(n.id())) {
        n.addClass("affected");
        n.removeClass("faded");
      } else {
        n.addClass("faded");
        n.removeClass("affected");
      }
    });
    cy.edges().forEach((e) => {
      if (affectedEdges.has(e.id())) {
        e.addClass("affected");
        e.removeClass("faded");
      } else {
        e.addClass("faded");
        e.removeClass("affected");
      }
    });
    // Strongest ring for impacted services.
    serviceIds.forEach((id) => {
      const node = cy.getElementById(id);
      if (node.nonempty()) node.addClass("impacted");
    });
  });
}

/**
 * Remove the persistent affected/faded highlight (FIX 6) added by
 * `highlightAffectedSubgraph`, restoring the normal (un-dimmed) graph. Kept
 * separate from the trail state so callers can compose them.
 */
export function clearHighlight(cy: Core): void {
  cy.elements().removeClass("affected");
  cy.elements().removeClass("faded");
}

/** Remove all traversal/impacted/affected highlight state and transient dots. */
export function clearTraversal(cy: Core): void {
  cy.edges().removeClass("traversal");
  cy.nodes().removeClass("impacted");
  cy.elements().removeClass("affected");
  cy.elements().removeClass("faded");
  cy.nodes(".blast-dot").remove();
  cy.nodes().forEach((n) => {
    n.removeStyle("border-width");
    n.removeStyle("width");
    n.removeStyle("height");
  });
}
