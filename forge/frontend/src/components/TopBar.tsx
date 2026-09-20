import { Menu, Share2 } from "lucide-react";
import HealthIndicator from "./HealthIndicator";

export type AppPage = "graph" | "analyst";

interface TopBarProps {
  onMenu?: () => void;
  page: AppPage;
  onPageChange: (page: AppPage) => void;
}

// Persistent top bar: logo left, page tabs center, health right.
export default function TopBar({ onMenu, page, onPageChange }: TopBarProps) {
  return (
    <header className="topbar">
      <div className="topbar-brand">
        {onMenu && (
          <button
            className="topbar-menu-btn"
            onClick={onMenu}
            aria-label="Toggle menu"
          >
            <Menu size={20} strokeWidth={1.5} />
          </button>
        )}
        <span className="topbar-mark" aria-hidden="true">
          <Share2 size={18} strokeWidth={1.5} />
        </span>
        <span className="topbar-wordmark">Forge</span>
      </div>

      <nav className="topbar-tabs" aria-label="App pages">
        <button
          className={`topbar-tab ${page === "graph" ? "active" : ""}`}
          onClick={() => onPageChange("graph")}
        >
          Graph Explorer
        </button>
        <button
          className={`topbar-tab ${page === "analyst" ? "active" : ""}`}
          onClick={() => onPageChange("analyst")}
        >
          Impact Analyst
        </button>
      </nav>

      <HealthIndicator />
    </header>
  );
}
