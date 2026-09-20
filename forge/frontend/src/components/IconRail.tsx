import { Upload, ListTree } from "lucide-react";

export type RailPanel = "ingest" | "legend" | null;

// Persistent left icon rail: two buttons that toggle overlay panels over the
// canvas without shifting layout.
export default function IconRail({
  active,
  onToggle,
  mobileOpen,
}: {
  active: RailPanel;
  onToggle: (panel: Exclude<RailPanel, null>) => void;
  mobileOpen?: boolean;
}) {
  return (
    <nav className={`icon-rail ${mobileOpen ? "mobile-open" : ""}`} aria-label="Tools">
      <button
        className={`rail-btn ${active === "ingest" ? "active" : ""}`}
        onClick={() => onToggle("ingest")}
        aria-label="Ingest repository"
        aria-pressed={active === "ingest"}
        title="Ingest"
      >
        <Upload size={20} strokeWidth={1.5} />
      </button>
      <button
        className={`rail-btn ${active === "legend" ? "active" : ""}`}
        onClick={() => onToggle("legend")}
        aria-label="Legend"
        aria-pressed={active === "legend"}
        title="Legend"
      >
        <ListTree size={20} strokeWidth={1.5} />
      </button>
    </nav>
  );
}
