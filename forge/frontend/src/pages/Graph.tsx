import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { ListTree, Info, HelpCircle, Layers } from "lucide-react";
import { Page, Header, Card, Button } from "../components/ui";
import GraphCanvas, { type GraphCanvasHandle } from "../graph/GraphCanvas";
import { LEVEL_STYLES } from "../graph/cytoConfig";
import HowItWorks from "../components/HowItWorks";
import EnrichmentPanel from "../components/EnrichmentPanel";
import { getGraphStats } from "../api";

export default function Graph() {
  const canvasRef = useRef<GraphCanvasHandle>(null);
  const [selected, setSelected] = useState<{ id: string; label: string; level: string } | null>(null);
  const [showLegend, setShowLegend] = useState(false);
  const [showHowItWorks, setShowHowItWorks] = useState(false);
  const [showEnrichment, setShowEnrichment] = useState(false);
  const [stats, setStats] = useState({ services: 0, symbols: 0, edges: 0 });

  useEffect(() => {
    getGraphStats().then(setStats).catch(console.error);
  }, []);

  const handleSelectNode = useCallback((node: { id: string; label: string; level: string } | null) => {
    setSelected(node);
  }, []);

  const handleExpand = useCallback(() => {
    if (selected) {
      canvasRef.current?.expandNodeById(selected.id);
    }
  }, [selected]);

  const handleFocus = useCallback(() => {
    if (selected) {
      canvasRef.current?.focusOnPath([selected.id]);
    }
  }, [selected]);

  return (
    <Page className="flex flex-col">
      <Header backTo="/" backLabel="Dashboard" title="Graph Explorer" />

      <div className="flex-1 flex gap-4 min-h-0">
        {/* Main Graph Area */}
        <div className="flex-1 relative min-h-0">
          <div className="absolute inset-0">
            <Card className="h-full p-0 overflow-hidden relative">
              <GraphCanvas
                ref={canvasRef}
                onSelectNode={handleSelectNode}
                reloadSignal={0}
              />
            </Card>
          </div>

          {/* Legend Toggle */}
          <div className="absolute bottom-4 left-4 flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setShowLegend(!showLegend)}
              icon={<ListTree size={14} />}
            >
              Legend
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setShowHowItWorks(true)}
              icon={<HelpCircle size={14} />}
            >
              How it works
            </Button>
            <Button
              variant={showEnrichment ? "primary" : "secondary"}
              size="sm"
              onClick={() => setShowEnrichment(!showEnrichment)}
              icon={<Layers size={14} />}
            >
              Dependencies
            </Button>
          </div>

          {/* Legend Panel */}
          {showLegend && (
            <motion.div
              className="absolute bottom-16 left-4 z-10"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
            >
              <Card className="w-64">
                <h3 className="font-medium text-sm mb-3">Node Types</h3>
                <div className="space-y-2">
                  {Object.entries(LEVEL_STYLES).map(([level, style]) => (
                    <div key={level} className="flex items-center gap-3">
                      <span
                        className="w-3 h-3 rounded-full"
                        style={{ backgroundColor: style.fill }}
                      />
                      <span className="text-sm text-[var(--color-text-secondary)] capitalize">
                        {level}
                      </span>
                    </div>
                  ))}
                </div>
                <div className="divider" />
                <h3 className="font-medium text-sm mb-3">Edge Types</h3>
                <div className="space-y-2">
                  <div className="flex items-center gap-3">
                    <span className="w-5 h-0.5 bg-[var(--color-text-muted)]" />
                    <span className="text-sm text-[var(--color-text-secondary)]">
                      Exact (internal)
                    </span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="w-5 h-0.5 border-t-2 border-dashed border-[var(--color-text-muted)]" />
                    <span className="text-sm text-[var(--color-text-secondary)]">
                      Inferred (cross-service)
                    </span>
                  </div>
                </div>
              </Card>
            </motion.div>
          )}
        </div>

        {/* Right Panel */}
        <div className="w-80 flex flex-col gap-3 overflow-y-auto min-h-0">

          {/* Enrichment panel — shown when Dependencies button is active */}
          {showEnrichment && (
            <motion.div
              className="flex-1 min-h-0"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
            >
              <EnrichmentPanel />
            </motion.div>
          )}

          {/* Node details panel — always shown when a node is selected */}
          {selected && !showEnrichment && (
            <motion.div
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
            >
              <Card className="h-full">
                <div className="flex items-center gap-3 mb-4">
                  <span
                    className="w-3 h-3 rounded-full"
                    style={{
                      backgroundColor: LEVEL_STYLES[selected.level]?.fill || "#666",
                    }}
                  />
                  <h2 className="font-semibold text-[var(--color-text-primary)] truncate">
                    {selected.label}
                  </h2>
                </div>

                <div className="space-y-3 text-sm">
                  <div>
                    <span className="text-[var(--color-text-muted)]">Type:</span>
                    <span className="ml-2 text-[var(--color-text-primary)] capitalize">
                      {selected.level}
                    </span>
                  </div>
                  <div>
                    <span className="text-[var(--color-text-muted)]">ID:</span>
                    <code className="ml-2 text-xs text-[var(--color-text-secondary)] break-all">
                      {selected.id}
                    </code>
                  </div>
                </div>

                <div className="divider" />

                <div className="space-y-2">
                  <Button
                    variant="secondary"
                    className="w-full"
                    onClick={handleExpand}
                  >
                    Expand Children
                  </Button>
                  <Button
                    variant="ghost"
                    className="w-full"
                    onClick={handleFocus}
                  >
                    Focus in Graph
                  </Button>
                </div>
              </Card>
            </motion.div>
          )}

          {/* Placeholder when nothing selected and enrichment off */}
          {!selected && !showEnrichment && (
            <Card className="h-full flex flex-col items-center justify-center text-center p-8">
              <Info size={32} className="text-[var(--color-text-muted)] mb-4 opacity-50" />
              <p className="text-[var(--color-text-muted)] text-sm">
                Click a node to see details
              </p>
              <p className="text-[var(--color-text-muted)] text-xs mt-2 opacity-70">
                Or click "Dependencies" to explore packages, DB tables, API endpoints, and env vars
              </p>
            </Card>
          )}
        </div>
      </div>

      {/* How it Works Modal */}
      <HowItWorks
        open={showHowItWorks}
        onClose={() => setShowHowItWorks(false)}
        stats={stats}
      />
    </Page>
  );
}
