import { useEffect, useRef, useState } from "react";
import { ArrowRight, Search } from "lucide-react";
import { Chip } from "./primitives";

const EXAMPLE_QUERIES: readonly string[] = [
  "What breaks if I change the currency field in the gateway?",
  "What services are impacted if the payment processor changes?",
  "Who consumes the payments topic?",
];

interface CommandBarProps {
  running: boolean;
  // Whether the results sheet is open (so we lift the bar above it).
  resultsOpen: boolean;
  // Whether any example chips should show (only when idle + no result yet).
  showChips: boolean;
  onSubmit: (question: string) => void;
}

// Floating pill command bar. Cmd/Ctrl+K focuses the input from anywhere. A slim
// indeterminate progress bar appears under it while a query runs.
export default function CommandBar({
  running,
  resultsOpen,
  showChips,
  onSubmit,
}: CommandBarProps) {
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const submit = () => {
    if (!value.trim() || running) return;
    onSubmit(value);
  };

  return (
    <div className={`command-bar ${resultsOpen ? "raised" : ""}`}>
      {showChips && !resultsOpen && (
        <div className="command-chips">
          {EXAMPLE_QUERIES.map((ex) => (
            <Chip
              key={ex}
              variant="outline"
              onClick={() => {
                setValue(ex);
                onSubmit(ex);
              }}
              title={ex}
            >
              {ex}
            </Chip>
          ))}
        </div>
      )}

      <div className="command-input-wrap">
        <Search className="command-input-icon" size={18} strokeWidth={1.5} />
        <input
          ref={inputRef}
          className="command-input"
          type="text"
          value={value}
          placeholder="Ask what breaks if you change something…"
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit();
          }}
          disabled={running}
          aria-label="Blast-radius query"
        />
        <span className="command-kbd" aria-hidden="true">
          ⌘K
        </span>
        <button
          className="command-ask"
          onClick={submit}
          disabled={running || !value.trim()}
        >
          {running ? (
            <>
              <span className="spinner spinner-sm" /> Tracing
            </>
          ) : (
            <>
              Ask <ArrowRight size={16} strokeWidth={2} />
            </>
          )}
        </button>

        {running && <div className="command-progress" />}
      </div>
    </div>
  );
}
