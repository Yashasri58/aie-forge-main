/**
 * ConfidenceBadge — displays a CONFIRMED / INFERRED / GAP tag
 * Used in the spec viewer to show claim provenance.
 */

import type { REConfidence } from "../types";

interface ConfidenceBadgeProps {
  confidence: REConfidence | string;
  size?: "sm" | "md";
}

const CONFIG: Record<string, { label: string; bg: string; text: string; border: string }> = {
  CONFIRMED: {
    label: "CONFIRMED",
    bg: "bg-emerald-900/40",
    text: "text-emerald-300",
    border: "border-emerald-600/50",
  },
  INFERRED: {
    label: "INFERRED",
    bg: "bg-amber-900/40",
    text: "text-amber-300",
    border: "border-amber-600/50",
  },
  GAP: {
    label: "GAP",
    bg: "bg-red-900/40",
    text: "text-red-300",
    border: "border-red-600/50",
  },
};

export default function ConfidenceBadge({
  confidence,
  size = "sm",
}: ConfidenceBadgeProps) {
  const cfg = CONFIG[confidence?.toUpperCase()] ?? CONFIG.GAP;
  const padding = size === "sm" ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-1 text-xs";

  return (
    <span
      className={`inline-flex items-center rounded border font-mono font-semibold tracking-wide ${padding} ${cfg.bg} ${cfg.text} ${cfg.border}`}
    >
      {cfg.label}
    </span>
  );
}
