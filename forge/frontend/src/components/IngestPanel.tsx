import { useEffect, useRef, useState } from "react";
import { AlertCircle, UploadCloud } from "lucide-react";
import { ingestFolder, ingestGit, ingestZip } from "../api";
import type { IngestionSummary } from "../types";
import { StatusBanner } from "./primitives";

type Mode = "folder" | "git" | "zip";

interface IngestPanelProps {
  // Fired after a successful ingest so the parent can reload the top graph and
  // fit the camera to the new nodes.
  onIngested: (summary: IngestionSummary) => void;
  // Fired when the user clicks "View in graph" on the success card.
  onViewInGraph: () => void;
}

// Ingestion controls inside the left overlay: Folder path / Git URL / Zip.
// Ingestion can take 1-2 minutes → clear loading state with elapsed counter.
export default function IngestPanel({ onIngested, onViewInGraph }: IngestPanelProps) {
  const [mode, setMode] = useState<Mode>("folder");
  const [location, setLocation] = useState("");
  const [repoName, setRepoName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<IngestionSummary | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Elapsed-seconds counter while ingesting.
  useEffect(() => {
    if (!busy) return;
    setElapsed(0);
    const id = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, [busy]);

  const canSubmit =
    !busy && (mode === "zip" ? file !== null : location.trim().length > 0);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      let result: IngestionSummary;
      if (mode === "folder") {
        result = await ingestFolder(location.trim(), repoName.trim());
      } else if (mode === "git") {
        result = await ingestGit(location.trim(), repoName.trim());
      } else {
        result = await ingestZip(file as File, repoName.trim());
      }
      setSummary(result);
      onIngested(result);
    } catch (err) {
      // Keep the form populated so the user can retry.
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  function resetForm() {
    setSummary(null);
    setError(null);
    setLocation("");
    setFile(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) setFile(f);
  }

  // --- Success card --------------------------------------------------------
  if (summary) {
    const repos = Array.isArray(summary.repos) ? summary.repos : [];
    return (
      <div className="summary-card">
        <div className="summary-stats">
          <div className="stat-box">
            <div className="stat-value">{repos.length}</div>
            <div className="stat-label">
              service{repos.length === 1 ? "" : "s"} added
            </div>
          </div>
          <div className="stat-box">
            <div className="stat-value">{summary.node_count ?? 0}</div>
            <div className="stat-label">nodes</div>
          </div>
          <div className="stat-box">
            <div className="stat-value">{summary.edge_count ?? 0}</div>
            <div className="stat-label">edges</div>
          </div>
          <div className="stat-box">
            <div className="stat-value">{summary.service_edge_count ?? 0}</div>
            <div className="stat-label">cross-service</div>
          </div>
        </div>

        {repos.map((repo) => (
          <div key={repo.repo_id}>
            <div className="summary-repo-name">{repo.repo_name || repo.repo_id}</div>
            <div className="lang-chips">
              {(repo.languages ?? []).map((lang) => (
                <span
                  key={lang.language}
                  className={`lang-chip ${
                    lang.tested ? "tested" : lang.available ? "available" : "skipped"
                  }`}
                  title={lang.detail || lang.status || ""}
                >
                  {lang.language}
                  {lang.tested ? " ✓" : lang.available ? "" : " ⚠"}
                </span>
              ))}
            </div>
          </div>
        ))}

        <button
          className="btn-primary"
          onClick={() => {
            onViewInGraph();
          }}
        >
          View in graph
        </button>
        <button className="btn-secondary" onClick={resetForm}>
          Ingest another
        </button>
      </div>
    );
  }

  // --- Form ----------------------------------------------------------------
  return (
    <form onSubmit={handleSubmit}>
      <div className="segmented" role="tablist">
        {(["folder", "git", "zip"] as Mode[]).map((m) => (
          <button
            key={m}
            type="button"
            role="tab"
            aria-selected={mode === m}
            className={`segmented-tab ${mode === m ? "active" : ""}`}
            onClick={() => setMode(m)}
            disabled={busy}
          >
            {m === "folder" ? "Folder path" : m === "git" ? "Git URL" : "Zip"}
          </button>
        ))}
      </div>

      {error && (
        <StatusBanner icon={<AlertCircle size={16} strokeWidth={1.5} />}>
          {error}
        </StatusBanner>
      )}

      {mode === "zip" ? (
        <div className="field">
          <span className="field-label">Zip archive</span>
          <div
            className={`dropzone ${dragging ? "dragging" : ""}`}
            onClick={() => fileInputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            role="button"
            tabIndex={0}
          >
            <UploadCloud size={24} strokeWidth={1.5} />
            {file ? (
              <span className="dropzone-file">{file.name}</span>
            ) : (
              <span>Drop a .zip here, or click to browse</span>
            )}
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".zip"
            style={{ display: "none" }}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            disabled={busy}
          />
        </div>
      ) : (
        <div className="field">
          <span className="field-label">
            {mode === "folder" ? "Folder path" : "Git URL"}
          </span>
          <input
            className="text-input mono"
            type="text"
            placeholder={
              mode === "folder"
                ? "C:\\repos\\service"
                : "https://github.com/org/repo"
            }
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            disabled={busy}
          />
        </div>
      )}

      <div className="field">
        <span className="field-label">Display name (optional)</span>
        <input
          className="text-input"
          type="text"
          placeholder="e.g. Inbound Gateway"
          value={repoName}
          onChange={(e) => setRepoName(e.target.value)}
          disabled={busy}
        />
      </div>

      <button type="submit" className="btn-primary" disabled={!canSubmit}>
        {busy ? (
          <>
            <span className="spinner spinner-sm" /> Ingesting…
          </>
        ) : (
          "Ingest"
        )}
      </button>

      {busy && (
        <p className="hint" style={{ marginTop: 12, marginBottom: 0 }}>
          Ingesting… this can take a minute or two.{" "}
          <span className="elapsed">{elapsed}s</span>
        </p>
      )}
    </form>
  );
}
