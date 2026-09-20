import type { ReactNode } from "react";
import { X } from "lucide-react";

// -----------------------------------------------------------------------------
// Small presentational primitives shared across panels/drawers.
// These are purely visual; no app behavior depends on them.
// -----------------------------------------------------------------------------

/** Generic side drawer that slides in over the canvas (does not shift layout). */
export function Drawer({
  side,
  open,
  title,
  icon,
  onClose,
  children,
}: {
  side: "left" | "right";
  open: boolean;
  title: string;
  icon?: ReactNode;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <aside
      className={`drawer ${side} ${open ? "" : "closed"}`}
      role="dialog"
      aria-label={title}
      aria-hidden={!open}
    >
      <div className="drawer-header">
        <div className="drawer-title">
          {icon}
          <span className="drawer-title-label">{title}</span>
        </div>
        <button className="icon-btn" onClick={onClose} aria-label="Close">
          <X size={18} strokeWidth={1.5} />
        </button>
      </div>
      <div className="drawer-body">{children}</div>
    </aside>
  );
}

/** Bottom sheet that slides up from the bottom (results drawer). */
export function BottomSheet({
  open,
  title,
  icon,
  onClose,
  children,
}: {
  open: boolean;
  title: ReactNode;
  icon?: ReactNode;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <section
      className={`bottom-sheet ${open ? "" : "closed"}`}
      role="dialog"
      aria-label="Query results"
      aria-hidden={!open}
    >
      <div className="bottom-sheet-header">
        <div className="drawer-title">
          {icon}
          <span className="drawer-title-label">{title}</span>
        </div>
        <button className="icon-btn" onClick={onClose} aria-label="Dismiss results">
          <X size={18} strokeWidth={1.5} />
        </button>
      </div>
      <div className="bottom-sheet-body">{children}</div>
    </section>
  );
}

/** A pill-shaped chip. Optionally clickable, with variant styling. */
export function Chip({
  children,
  onClick,
  variant,
  title,
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "outline" | "impacted";
  title?: string;
}) {
  const cls = [
    "chip",
    variant ?? "",
    onClick ? "clickable" : "",
  ]
    .filter(Boolean)
    .join(" ");
  if (onClick) {
    return (
      <button type="button" className={cls} onClick={onClick} title={title}>
        {children}
      </button>
    );
  }
  return (
    <span className={cls} title={title}>
      {children}
    </span>
  );
}

/** Inline error/status banner. */
export function StatusBanner({
  children,
  icon,
}: {
  children: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="banner error" role="alert">
      {icon && <span className="banner-icon">{icon}</span>}
      <span>{children}</span>
    </div>
  );
}
