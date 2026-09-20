/**
 * ReverseEngineer — Upload page (Pipeline 3 entry point).
 *
 * User uploads a log file + optional text comments.
 * On submit, starts the pipeline and navigates to /reverse-engineer/:id/pipeline.
 *
 * Visual style matches the rest of the Forge UI (dark theme, same card / button classes).
 */

import { useState, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { HelpCircle } from "lucide-react";
import { startReverseEngineer } from "../api";
import HowREWorks from "../components/HowREWorks";

export default function ReverseEngineer() {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [comments, setComments] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [showHowItWorks, setShowHowItWorks] = useState(false);

  // ─── File handling ───────────────────────────────────────────────────────

  const acceptFile = (f: File) => {
    const allowed = [".log", ".txt", ".jsonl", ".json", ".csv", ".tsv"];
    const ext = "." + f.name.split(".").pop()?.toLowerCase();
    if (!allowed.includes(ext)) {
      setError(`File type "${ext}" not supported. Use: ${allowed.join(", ")}`);
      return;
    }
    setFile(f);
    setError(null);
  };

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) acceptFile(f);
  };

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) acceptFile(f);
  }, []);

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(true);
  };

  const onDragLeave = () => setDragging(false);

  // ─── Submit ──────────────────────────────────────────────────────────────

  const handleSubmit = async () => {
    if (!file) {
      setError("Please select a log file.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const session = await startReverseEngineer(file, comments || undefined);
      navigate(`/reverse-engineer/${session.id}/pipeline`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to start pipeline");
    } finally {
      setLoading(false);
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
  };

  // ─── Render ──────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-[#0d1117] text-gray-100 flex flex-col">
      {/* Top bar */}
      <header className="flex items-center gap-3 px-6 py-4 border-b border-white/10">
        <button
          onClick={() => navigate("/")}
          className="text-gray-400 hover:text-white transition-colors text-sm"
        >
          ← Dashboard
        </button>
        <span className="text-gray-600">/</span>
        <span className="text-gray-300 font-medium">Reverse Engineer</span>
        <div className="flex-1" />
        <button
          onClick={() => setShowHowItWorks(true)}
          className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-white transition-colors px-3 py-1.5 rounded-lg hover:bg-white/5"
        >
          <HelpCircle size={14} />
          How it Works
        </button>
      </header>

      {/* How it Works modal */}
      <HowREWorks open={showHowItWorks} onClose={() => setShowHowItWorks(false)} />

      <main className="flex-1 flex items-center justify-center p-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="w-full max-w-2xl space-y-6"
        >
          {/* Title */}
          <div className="text-center space-y-2">
            <div className="text-4xl mb-2">🔍</div>
            <h1 className="text-2xl font-bold text-white">Reverse Engineer</h1>
            <p className="text-gray-400 text-sm max-w-md mx-auto">
              Upload a structured log file from a third-party application. Forge
              will automatically produce a complete specification document — no
              source code needed.
            </p>
          </div>

          {/* Drop zone */}
          <div
            onClick={() => fileInputRef.current?.click()}
            onDrop={onDrop}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            className={`
              relative cursor-pointer rounded-xl border-2 border-dashed p-10
              flex flex-col items-center gap-3 transition-all
              ${dragging
                ? "border-blue-400 bg-blue-950/30"
                : file
                ? "border-emerald-500/60 bg-emerald-950/20"
                : "border-white/20 hover:border-white/40 bg-white/5"
              }
            `}
          >
            <input
              ref={fileInputRef}
              type="file"
              className="hidden"
              accept=".log,.txt,.jsonl,.json,.csv,.tsv"
              onChange={onFileChange}
            />

            {file ? (
              <>
                <div className="text-3xl">📄</div>
                <div className="text-center">
                  <p className="text-emerald-300 font-medium">{file.name}</p>
                  <p className="text-gray-400 text-sm">
                    {formatSize(file.size)} · Click to change
                  </p>
                </div>
              </>
            ) : (
              <>
                <div className="text-3xl text-gray-500">📁</div>
                <div className="text-center">
                  <p className="text-gray-300 font-medium">
                    Drop log file here or click to browse
                  </p>
                  <p className="text-gray-500 text-xs mt-1">
                    .log · .txt · .jsonl · .json · .csv · .tsv
                  </p>
                </div>
              </>
            )}
          </div>

          {/* User comments */}
          <div className="space-y-2">
            <label className="block text-sm font-medium text-gray-300">
              Context about this application{" "}
              <span className="text-gray-500 font-normal">(optional)</span>
            </label>
            <textarea
              value={comments}
              onChange={(e) => setComments(e.target.value)}
              placeholder={
                "E.g. This is a payment processing system. The api-gateway handles all external traffic. " +
                "Service X is responsible for fraud detection."
              }
              rows={4}
              className={`
                w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3
                text-sm text-gray-200 placeholder-gray-500
                focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500
                resize-none transition-colors
              `}
            />
            <p className="text-xs text-gray-500">
              Additional context helps the AI produce more accurate business logic descriptions.
              This information is sanitized and never stored beyond this session.
            </p>
          </div>

          {/* Error */}
          {error && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="rounded-lg bg-red-950/50 border border-red-500/30 px-4 py-3 text-sm text-red-300"
            >
              {error}
            </motion.div>
          )}

          {/* Submit */}
          <button
            onClick={handleSubmit}
            disabled={!file || loading}
            className={`
              w-full py-3 rounded-xl font-semibold text-sm transition-all
              ${!file || loading
                ? "bg-gray-700 text-gray-400 cursor-not-allowed"
                : "bg-blue-600 hover:bg-blue-500 text-white shadow-lg shadow-blue-900/30"
              }
            `}
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <span className="h-4 w-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
                Starting pipeline…
              </span>
            ) : (
              "Start Reverse Engineering →"
            )}
          </button>

          {/* Info strip */}
          <div className="grid grid-cols-3 gap-3 text-center">
            {[
              { icon: "⚡", label: "Stage 1–2", desc: "Deterministic parsing" },
              { icon: "🧠", label: "Stage 3–4", desc: "AI inference + gap review" },
              { icon: "📝", label: "Stage 5", desc: "11 spec sections" },
            ].map((item) => (
              <div
                key={item.label}
                className="rounded-lg border border-white/10 bg-white/5 p-3 space-y-1"
              >
                <div className="text-xl">{item.icon}</div>
                <div className="text-xs font-semibold text-gray-300">{item.label}</div>
                <div className="text-xs text-gray-500">{item.desc}</div>
              </div>
            ))}
          </div>
        </motion.div>
      </main>
    </div>
  );
}
