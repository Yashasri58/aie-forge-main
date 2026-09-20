import { useCallback, useEffect, useRef, useState } from "react";
import { getHealth, type HealthResponse } from "../api";

// Top-bar health indicator: dot + label Connected/Degraded/Offline. Polls every
// 20s. Click reveals a tooltip with the last-checked time.

type Status = "ok" | "warn" | "error" | "pending";

const POLL_MS = 20_000;

export default function HealthIndicator() {
  const [status, setStatus] = useState<Status>("pending");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);
  const [showTip, setShowTip] = useState(false);
  const tipTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const check = useCallback(async () => {
    try {
      const data = await getHealth();
      setHealth(data);
      // "Degraded" (warn) when reachable but reporting a non-ok status string.
      setStatus(data.status && data.status !== "ok" ? "warn" : "ok");
    } catch {
      setHealth(null);
      setStatus("error");
    } finally {
      setLastChecked(new Date());
    }
  }, []);

  useEffect(() => {
    void check();
    const id = setInterval(() => void check(), POLL_MS);
    return () => clearInterval(id);
  }, [check]);

  const label =
    status === "pending"
      ? "Checking…"
      : status === "ok"
        ? "Connected"
        : status === "warn"
          ? "Degraded"
          : "Offline";

  const onClick = () => {
    setShowTip((s) => !s);
    if (tipTimer.current) clearTimeout(tipTimer.current);
    tipTimer.current = setTimeout(() => setShowTip(false), 4000);
  };

  const detail =
    status === "ok" && health
      ? `Backend v${health.version} · LLM ${health.llm_enabled ? "on" : "off"}`
      : status === "warn"
        ? "Backend reachable but degraded"
        : status === "error"
          ? "Backend unreachable"
          : "Contacting backend…";

  return (
    <button className="health" onClick={onClick} title="Backend health">
      <span className={`health-dot ${status === "pending" ? "" : status}`} />
      <span className="health-label">{label}</span>
      {showTip && (
        <span className="health-tooltip">
          {detail}
          {lastChecked && (
            <> · checked {lastChecked.toLocaleTimeString()}</>
          )}
        </span>
      )}
    </button>
  );
}
