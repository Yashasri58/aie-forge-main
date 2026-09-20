import type { ReactNode } from "react";
import { CheckCircle2, Zap } from "lucide-react";
import type { GraceResultDto } from "../types";
import { BottomSheet, Chip } from "./primitives";

interface ResultsDrawerProps {
  open: boolean;
  result: GraceResultDto | null;
  onClose: () => void;
  onFocusService: (id: string) => void;
}

// Render the deterministic structural summary as clean prose + bullets,
// respecting the newlines and "•" bullet markers the backend emits. Falls back
// to the raw serialized_context (monospace) only when the summary is empty.
function SummaryBody({
  summary,
  fallback,
}: {
  summary: string;
  fallback: string;
}) {
  const text = summary.trim();
  if (!text) {
    return <pre className="results-context">{fallback}</pre>;
  }

  // Group consecutive bullet lines ("• ...") into <ul>; everything else renders
  // as a paragraph. Blank lines separate blocks.
  const lines = text.split("\n");
  const blocks: ReactNode[] = [];
  let bullets: string[] = [];

  const flushBullets = () => {
    if (bullets.length === 0) return;
    blocks.push(
      <ul className="results-summary-list" key={`ul-${blocks.length}`}>
        {bullets.map((b, i) => (
          <li key={i}>{b}</li>
        ))}
      </ul>,
    );
    bullets = [];
  };

  for (const raw of lines) {
    const line = raw.trimEnd();
    const trimmed = line.trim();
    if (trimmed.startsWith("\u2022")) {
      bullets.push(trimmed.replace(/^\u2022\s*/, ""));
      continue;
    }
    flushBullets();
    if (trimmed === "") continue;
    // A short label line ending in ":" reads as an emphasized heading.
    const isHeading = /:$/.test(trimmed) && trimmed.length < 60;
    blocks.push(
      <p
        className={`results-summary-line${isHeading ? " results-summary-heading" : ""}`}
        key={`p-${blocks.length}`}
      >
        {trimmed}
      </p>,
    );
  }
  flushBullets();

  return <div className="results-summary">{blocks}</div>;
}

// Bottom sheet that slides up when a blast-radius query returns. Shows the
// impacted-service count as a big stat, clickable service chips, and the answer
// body (LLM prose if present, else the structural summary).
export default function ResultsDrawer({
  open,
  result,
  onClose,
  onFocusService,
}: ResultsDrawerProps) {
  const impacted = result?.impacted_services ?? [];
  const hasLlm = result != null && result.llm_answer != null;
  const noImpact = result != null && impacted.length === 0;

  return (
    <BottomSheet
      open={open}
      icon={<Zap size={16} strokeWidth={1.5} />}
      title="Blast radius"
      onClose={onClose}
    >
      {result && (
        <>
          <div className="results-stat">
            <span className="results-stat-value">{impacted.length}</span>
            <span className="results-stat-label">
              service{impacted.length === 1 ? "" : "s"} impacted
            </span>
          </div>

          {noImpact ? (
            <div className="results-empty">
              <CheckCircle2 size={18} strokeWidth={1.5} />
              No downstream impact detected.
            </div>
          ) : (
            <>
              <div className="results-section-title">Impacted services</div>
              <div className="results-chips">
                {impacted.map((svc) => (
                  <Chip
                    key={svc}
                    variant="impacted"
                    onClick={() => onFocusService(svc)}
                    title={`Focus ${svc}`}
                  >
                    {svc}
                  </Chip>
                ))}
              </div>
            </>
          )}

          <div className="results-section-title">
            {hasLlm ? "Answer" : "Structural summary"}
            <span className={`results-tag ${hasLlm ? "ai" : "structural"}`}>
              {hasLlm ? "AI answer" : "Structural summary"}
            </span>
          </div>
          {hasLlm ? (
            <p className="results-answer">{result.llm_answer}</p>
          ) : (
            <SummaryBody
              summary={result.summary ?? ""}
              fallback={result.serialized_context}
            />
          )}
        </>
      )}
    </BottomSheet>
  );
}
