import { forwardRef, type ReactNode, type ButtonHTMLAttributes } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { clsx } from "clsx";
import {
  ArrowLeft,
  GitGraph,
  Loader2,
  CheckCircle2,
  AlertCircle,
  Info,
} from "lucide-react";

/* ═══════════════════════════════════════════════════════════════════════════
   Page Layout Components
   ═══════════════════════════════════════════════════════════════════════════ */

interface PageProps {
  children: ReactNode;
  className?: string;
}

export function Page({ children, className }: PageProps) {
  return (
    <motion.div
      className={clsx("page", className)}
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
    >
      {children}
    </motion.div>
  );
}

interface HeaderProps {
  title?: string;
  backTo?: string;
  backLabel?: string;
  step?: { current: number; total: number; label: string };
  children?: ReactNode;
}

export function Header({ title, backTo, backLabel, step, children }: HeaderProps) {
  return (
    <header className="header">
      <div className="flex items-center gap-4">
        {backTo && (
          <Link
            to={backTo}
            className="flex items-center gap-2 text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors"
          >
            <ArrowLeft size={16} />
            {backLabel || "Back"}
          </Link>
        )}
        {title && (
          <h1 className="text-xl font-semibold text-[var(--color-text-primary)]">
            {title}
          </h1>
        )}
      </div>

      {step && (
        <div className="steps">
          {Array.from({ length: step.total }, (_, i) => (
            <div key={i} className="flex items-center gap-2">
              {i > 0 && <div className="step-connector" />}
              <div
                className={clsx(
                  "step",
                  i + 1 === step.current && "step-active",
                  i + 1 < step.current && "step-complete"
                )}
              >
                {i + 1 < step.current ? (
                  <CheckCircle2 size={14} />
                ) : (
                  <span className="w-5 h-5 rounded-full border border-current flex items-center justify-center text-xs">
                    {i + 1}
                  </span>
                )}
                {i + 1 === step.current && (
                  <span className="font-medium">{step.label}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="flex items-center gap-3">
        {children}
        <Link
          to="/explore"
          className="btn btn-ghost text-sm"
        >
          <GitGraph size={16} />
          View Graph
        </Link>
      </div>
    </header>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   Button Component
   ═══════════════════════════════════════════════════════════════════════════ */

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "success" | "danger";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
  icon?: ReactNode;
  children: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "primary", size = "md", loading, icon, children, className, disabled, ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={clsx(
          "btn",
          `btn-${variant}`,
          size === "lg" && "btn-lg",
          size === "sm" && "px-3 py-1.5 text-xs",
          className
        )}
        disabled={disabled || loading}
        {...props}
      >
        {loading ? (
          <Loader2 size={16} className="animate-spin" />
        ) : icon ? (
          icon
        ) : null}
        {children}
      </button>
    );
  }
);
Button.displayName = "Button";

/* ═══════════════════════════════════════════════════════════════════════════
   Card Component
   ═══════════════════════════════════════════════════════════════════════════ */

interface CardProps {
  children: ReactNode;
  className?: string;
  hover?: boolean;
  onClick?: () => void;
}

export function Card({ children, className, hover, onClick }: CardProps) {
  return (
    <div
      className={clsx("card", hover && "card-hover cursor-pointer", className)}
      onClick={onClick}
    >
      {children}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   Stat Card Component
   ═══════════════════════════════════════════════════════════════════════════ */

interface StatCardProps {
  value: string | number;
  label: string;
  icon?: ReactNode;
  trend?: "up" | "down" | "neutral";
}

export function StatCard({ value, label, icon }: StatCardProps) {
  return (
    <Card className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="stat-value">{value}</span>
        {icon && (
          <span className="text-[var(--color-text-muted)]">{icon}</span>
        )}
      </div>
      <span className="text-sm text-[var(--color-text-muted)]">{label}</span>
    </Card>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   Badge Component
   ═══════════════════════════════════════════════════════════════════════════ */

interface BadgeProps {
  variant?: "default" | "accent" | "success" | "warning" | "error";
  children: ReactNode;
  className?: string;
}

export function Badge({ variant = "default", children, className }: BadgeProps) {
  return (
    <span
      className={clsx(
        "badge",
        variant !== "default" && `badge-${variant}`,
        className
      )}
    >
      {children}
    </span>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   Progress Bar Component
   ═══════════════════════════════════════════════════════════════════════════ */

interface ProgressProps {
  value: number;
  max?: number;
  className?: string;
}

export function Progress({ value, max = 100, className }: ProgressProps) {
  const percentage = Math.min(100, Math.max(0, (value / max) * 100));
  return (
    <div className={clsx("progress", className)}>
      <div className="progress-fill" style={{ width: `${percentage}%` }} />
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   Alert Component
   ═══════════════════════════════════════════════════════════════════════════ */

interface AlertProps {
  variant?: "info" | "success" | "warning" | "error";
  title?: string;
  children: ReactNode;
  className?: string;
}

export function Alert({ variant = "info", title, children, className }: AlertProps) {
  const Icon = variant === "success" ? CheckCircle2 
    : variant === "error" ? AlertCircle 
    : variant === "warning" ? AlertCircle 
    : Info;

  const colors = {
    info: "border-[var(--color-accent)] bg-[var(--color-accent-subtle)]",
    success: "border-[var(--color-success)] bg-[var(--color-success-subtle)]",
    warning: "border-[var(--color-warning)] bg-[var(--color-warning-subtle)]",
    error: "border-[var(--color-error)] bg-[var(--color-error-subtle)]",
  };

  return (
    <div className={clsx("flex gap-3 p-4 rounded-lg border-l-4", colors[variant], className)}>
      <Icon size={20} className="flex-shrink-0 mt-0.5" />
      <div>
        {title && <div className="font-medium mb-1">{title}</div>}
        <div className="text-sm text-[var(--color-text-secondary)]">{children}</div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   Spinner Component
   ═══════════════════════════════════════════════════════════════════════════ */

interface SpinnerProps {
  size?: "sm" | "md" | "lg";
  className?: string;
}

export function Spinner({ size = "md", className }: SpinnerProps) {
  const sizes = { sm: 16, md: 24, lg: 40 };
  return (
    <Loader2
      size={sizes[size]}
      className={clsx("animate-spin text-[var(--color-accent)]", className)}
    />
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   Status Dot Component
   ═══════════════════════════════════════════════════════════════════════════ */

interface StatusDotProps {
  status: "online" | "warning" | "error" | "offline";
  pulse?: boolean;
}

export function StatusDot({ status, pulse }: StatusDotProps) {
  const colors = {
    online: "status-dot",
    warning: "status-dot status-dot-warning",
    error: "status-dot status-dot-error",
    offline: "w-2 h-2 rounded-full bg-[var(--color-text-muted)]",
  };

  return (
    <span className={clsx(colors[status], pulse && "pulse-glow")} />
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   Empty State Component
   ═══════════════════════════════════════════════════════════════════════════ */

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="empty-state">
      {icon && <div className="empty-state-icon">{icon}</div>}
      <h3 className="empty-state-title">{title}</h3>
      {description && <p className="empty-state-description">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   Logo Component
   ═══════════════════════════════════════════════════════════════════════════ */

export function Logo({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
  const sizes = { sm: "text-lg", md: "text-2xl", lg: "text-4xl" };
  return (
    <Link to="/" className={clsx("font-bold tracking-tight", sizes[size])}>
      <span className="text-gradient">FORGE</span>
    </Link>
  );
}
