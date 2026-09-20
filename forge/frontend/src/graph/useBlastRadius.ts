import { useCallback, useRef, useState } from "react";
import { runGraceQuery } from "../api";
import type { GraceResultDto } from "../types";
import type { GraphCanvasHandle } from "./GraphCanvas";
import {
  animateTraversal,
  clearTraversal,
  highlightAffectedSubgraph,
  highlightImpactedServices,
  type TraversalAnimation,
} from "./animateTraversal";

// Coordinates a GRACE blast-radius query: run it, merge the returned subgraph
// onto the canvas, frame the impacted nodes, race the comet trail, then light
// up impacted services. Exposed to the CommandBar (submit) and the App (which
// renders the ResultsDrawer from `result`).
export function useBlastRadius(
  canvasRef: React.RefObject<GraphCanvasHandle | null>,
) {
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GraceResultDto | null>(null);
  const animRef = useRef<TraversalAnimation | null>(null);

  const run = useCallback(
    async (question: string) => {
      const trimmed = question.trim();
      if (!trimmed || running) return;
      setRunning(true);
      setError(null);

      animRef.current?.cancel();
      animRef.current = null;

      try {
        const res = await runGraceQuery(trimmed);
        setResult(res);

        const handle = canvasRef.current;
        if (handle) {
          // Merge the (possibly not-yet-rendered) subgraph BEFORE animating so
          // there are real elements to light up.
          handle.mergeView({ nodes: res.nodes, edges: res.edges });
          const cy = handle.getCy();
          if (cy) {
            clearTraversal(cy);
            handle.focusOnPath(res.traversal_path);
            // Give the camera a beat to fit before the trail starts.
            setTimeout(() => {
              const anim = animateTraversal(cy, res.traversal_path);
              animRef.current = anim;
              void anim.done.then(() => {
                // Comet landed: keep impacted services strongest, then light up
                // the WHOLE affected subgraph (every returned node + edge) and
                // fade the rest so the blast radius reads at a glance.
                highlightImpactedServices(cy, res.impacted_services);
                highlightAffectedSubgraph(
                  cy,
                  res.nodes.map((n) => n.id),
                  res.edges.map((e) => e.id),
                  res.impacted_services,
                );
              });
            }, 260);
          }
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
        setResult(null);
      } finally {
        setRunning(false);
      }
    },
    [canvasRef, running],
  );

  const focusService = useCallback(
    (id: string) => {
      canvasRef.current?.focusOnPath([id]);
    },
    [canvasRef],
  );

  const dismiss = useCallback(() => {
    const cy = canvasRef.current?.getCy();
    if (cy) clearTraversal(cy);
    setResult(null);
  }, [canvasRef]);

  return { running, error, result, run, focusService, dismiss };
}
