import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  GitGraph,
  Box,
  GitBranch,
  ArrowRight,
  Sparkles,
  Zap,
  ExternalLink,
  HelpCircle,
  Database,
  Trash2,
  Clock,
  Download,
} from "lucide-react";
import { Page, Card, StatCard, Button, Badge, StatusDot, Logo } from "../components/ui";
import HowForgeWorks from "../components/HowForgeWorks";
import { getGraphStats, listCache, deleteCacheEntry, type CacheEntry } from "../api";
import { entryToMarkdown, triggerDownload, safeFilename } from "../utils/downloadUtils";
import JSZip from "jszip";

interface ServiceOverview {
  id: string;
  name: string;
  functions: number;
  inbound: number;
  outbound: number;
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [stats, setStats] = useState({ services: 0, symbols: 0, edges: 0 });
  const [services, setServices] = useState<ServiceOverview[]>([]);
  const [loading, setLoading] = useState(true);
  const [showHowItWorks, setShowHowItWorks] = useState(false);
  const [cacheEntries, setCacheEntries] = useState<CacheEntry[]>([]);

  useEffect(() => {
    loadData();
    loadCache();
  }, []);

  async function loadCache() {
    try {
      const entries = await listCache();
      setCacheEntries(entries);
    } catch {
      // cache unavailable — not critical
    }
  }

  async function handleDeleteCache(id: string) {
    await deleteCacheEntry(id);
    setCacheEntries(prev => prev.filter(e => e.id !== id));
  }

  async function handleDownloadAll() {
    try {
      const results = await Promise.all(
        cacheEntries.map(async (entry) => {
          try {
            const res = await fetch(`/cache/${encodeURIComponent(entry.id)}`);
            return res.ok ? res.json() : { ...entry, _error: "failed to fetch" };
          } catch {
            return { ...entry, _error: "network error" };
          }
        })
      );

      const zip = new JSZip();
      const ts = new Date().toISOString().slice(0, 19).replace(/[T:]/g, "-");

      // One .md file per entry
      results.forEach((entry) => {
        const md = entryToMarkdown(entry);
        const filename = safeFilename(entry.label || entry.id, entry.id.slice(0, 8));
        zip.file(filename, md);
      });

      // Also include a summary index
      const index = results.map((e, i) =>
        `${i + 1}. [${e.pipeline_type?.toUpperCase()}] ${e.label || e.id}`
      ).join("\n");
      zip.file("_index.md", `# Forge History Export\nExported: ${ts}\nTotal: ${results.length} entries\n\n${index}\n`);

      const blob = await zip.generateAsync({ type: "blob" });
      triggerDownload(blob, `forge_history_${ts}.zip`, "application/zip");
    } catch (err) {
      console.error("Download all failed:", err);
    }
  }

  async function handleDownloadCache(id: string, label: string) {
    try {
      const res = await fetch(`/cache/${encodeURIComponent(id)}`);
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      const data = await res.json();
      const md = entryToMarkdown(data);
      triggerDownload(md, safeFilename(label, id.slice(0, 8)));
    } catch (err) {
      console.error("Download failed:", err);
    }
  }

  async function loadData() {
    try {
      const graphStats = await getGraphStats();
      setStats(graphStats);
      
      // Fetch service list from graph overview
      const res = await fetch("/graph/overview");
      const data = await res.json();
      
      // Extract services from nodes
      const serviceNodes = data.nodes?.filter((n: { type: string }) => n.type === "service") || [];
      const edges = data.edges || [];
      
      const serviceList: ServiceOverview[] = serviceNodes.map((node: { id: string; label: string; child_count?: number }) => {
        const inbound = edges.filter((e: { target: string }) => e.target === node.id).length;
        const outbound = edges.filter((e: { source: string }) => e.source === node.id).length;
        return {
          id: node.id,
          name: node.label,
          functions: node.child_count || 0,
          inbound,
          outbound,
        };
      });
      
      setServices(serviceList);
    } catch (err) {
      console.error("Failed to load dashboard data:", err);
    } finally {
      setLoading(false);
    }
  }

  async function handleStartAnalysis() {
    // Just navigate to chat page - don't start pipeline yet
    // Pipeline will start when user sends their first message
    navigate(`/chat/new`);
  }

  return (
    <Page>
      {/* Header */}
      <header className="flex items-center justify-between pb-6 border-b border-[var(--color-glass-border)] mb-6">
        <div className="flex items-center gap-6">
          <Logo />
          <div className="flex items-center gap-2">
            <StatusDot status="online" pulse />
            <span className="text-sm text-[var(--color-text-muted)]">
              Graph loaded
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            onClick={() => setShowHowItWorks(true)}
            icon={<HelpCircle size={16} />}
          >
            How it Works
          </Button>
          <Button
            variant="ghost"
            onClick={() => navigate("/explore")}
            icon={<GitGraph size={16} />}
          >
            View Graph
          </Button>
        </div>
      </header>

      {/* How Forge Works Modal */}
      <HowForgeWorks
        open={showHowItWorks}
        onClose={() => setShowHowItWorks(false)}
      />

      {/* Stats Row */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
        >
          <StatCard
            value={stats.services}
            label="Services"
            icon={<Box size={20} />}
          />
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
        >
          <StatCard
            value={stats.symbols}
            label="Functions"
            icon={<GitBranch size={20} />}
          />
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
        >
          <StatCard
            value={stats.edges}
            label="Connections"
            icon={<Zap size={20} />}
          />
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25 }}
        >
          <Card className="flex flex-col items-center justify-center gap-2 text-center">
            <Sparkles size={24} className="text-[var(--color-accent)]" />
            <span className="text-sm text-[var(--color-text-muted)]">
              AI-Powered Analysis
            </span>
          </Card>
        </motion.div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-h-0">
        {/* Services Table */}
        <motion.div
          className="flex-shrink-0"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
        >
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">
              Services Overview
            </h2>
            <Badge variant="accent">{services.length} services</Badge>
          </div>

          <Card className="overflow-hidden">
            {loading ? (
              <div className="flex items-center justify-center py-8">
                <div className="shimmer w-full h-12 rounded-lg" />
              </div>
            ) : services.length === 0 ? (
              <div className="flex flex-col items-center justify-center text-center p-8">
                <Box size={48} className="text-[var(--color-text-muted)] mb-4 opacity-50" />
                <p className="text-[var(--color-text-muted)]">
                  No services found. Ingest a repository to get started.
                </p>
              </div>
            ) : (
              <div className="overflow-auto" style={{ maxHeight: "260px" }}>
                <table className="table">
                  <thead>
                    <tr>
                      <th className="w-8"></th>
                      <th>Service</th>
                      <th className="text-right">Functions</th>
                      <th className="text-right">Inbound</th>
                      <th className="text-right">Outbound</th>
                      <th className="w-12"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {services.map((service, i) => (
                      <motion.tr
                        key={service.id}
                        initial={{ opacity: 0, x: -20 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: 0.05 * i }}
                        className="group"
                      >
                        <td>
                          <div
                            className="w-1 h-8 rounded-full"
                            style={{
                              background: `hsl(${(i * 45) % 360}, 70%, 60%)`,
                            }}
                          />
                        </td>
                        <td>
                          <span className="font-medium text-[var(--color-text-primary)] group-hover:text-[var(--color-accent)] transition-colors">
                            {service.name}
                          </span>
                        </td>
                        <td className="text-right font-mono">
                          {service.functions}
                        </td>
                        <td className="text-right font-mono text-[var(--color-success)]">
                          ↓ {service.inbound}
                        </td>
                        <td className="text-right font-mono text-[var(--color-accent)]">
                          ↑ {service.outbound}
                        </td>
                        <td>
                          <button
                            className="opacity-0 group-hover:opacity-100 transition-opacity text-[var(--color-text-muted)] hover:text-[var(--color-accent)]"
                            onClick={() => navigate(`/explore?focus=${service.id}`)}
                          >
                            <ExternalLink size={14} />
                          </button>
                        </td>
                      </motion.tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </motion.div>

        {/* Past Requests & Results panel */}
        {cacheEntries.length > 0 && (
          <motion.div
            className="mt-6"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.35 }}
          >
            {/* Panel header */}
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Database size={16} className="text-[var(--color-accent)]" />
                <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">
                  Past Requests & Results
                </h2>
                <Badge variant="accent">{cacheEntries.length}</Badge>
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={handleDownloadAll}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-[var(--color-glass-bg)] border border-[var(--color-glass-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-accent)] hover:border-[var(--color-accent)] transition-all"
                  title="Download all entries as a single JSON file"
                >
                  <Download size={13} />
                  Download All
                </button>
                <span className="text-xs text-[var(--color-text-muted)]">
                  Click row to view details
                </span>
              </div>
            </div>

            <Card className="overflow-hidden">
              <div className="divide-y divide-[var(--color-glass-border)]">
                {cacheEntries.map((entry) => {
                  const typeColors: Record<string, string> = {
                    impact: "text-blue-400",
                    codegen: "text-green-400",
                    reverse_engineer: "text-purple-400",
                  };
                  const typeLabels: Record<string, string> = {
                    impact: "Impact",
                    codegen: "CodeGen",
                    reverse_engineer: "RE",
                  };
                  const ago = Math.round((Date.now() / 1000 - entry.last_used_at) / 60);
                  const agoStr = ago < 60 ? `${ago}m ago` : `${Math.round(ago/60)}h ago`;

                  return (
                    <div
                      key={entry.id}
                      onClick={() => navigate(`/history/${entry.id}`)}
                      className="flex items-center gap-4 px-4 py-3 hover:bg-[var(--color-glass-bg)] transition-colors group cursor-pointer"
                    >
                      {/* Type badge */}
                      <span className={`text-xs font-mono font-bold w-16 shrink-0 ${typeColors[entry.pipeline_type] || "text-[var(--color-text-muted)]"}`}>
                        {typeLabels[entry.pipeline_type] || entry.pipeline_type}
                      </span>

                      {/* Label */}
                      <span className="flex-1 text-sm text-[var(--color-text-primary)] truncate group-hover:text-[var(--color-accent)] transition-colors">
                        {entry.label?.replace(/^\[REJECTED\]\s*/, "") ?? ""}
                      </span>
                      {entry.label?.startsWith("[REJECTED]") && (
                        <span className="shrink-0 px-1.5 py-0.5 rounded text-[10px] font-bold bg-[var(--color-error-subtle)] text-[var(--color-error)]">
                          REJECTED
                        </span>
                      )}

                      {/* Use count */}
                      {entry.use_count > 0 && (
                        <span className="text-xs text-[var(--color-text-muted)] shrink-0">
                          viewed {entry.use_count}×
                        </span>
                      )}

                      {/* Last used */}
                      <span className="text-xs text-[var(--color-text-muted)] shrink-0 flex items-center gap-1">
                        <Clock size={11} />
                        {agoStr}
                      </span>

                      {/* Arrow hint */}
                      <span className="opacity-0 group-hover:opacity-100 transition-opacity text-[var(--color-accent)] shrink-0 text-xs">
                        →
                      </span>

                      {/* Download */}
                      <button
                        onClick={(e) => { e.stopPropagation(); handleDownloadCache(entry.id, entry.label); }}
                        className="opacity-0 group-hover:opacity-100 transition-opacity text-[var(--color-text-muted)] hover:text-[var(--color-accent)] shrink-0"
                        title="Download as JSON"
                      >
                        <Download size={14} />
                      </button>

                      {/* Delete */}
                      <button
                        onClick={(e) => { e.stopPropagation(); handleDeleteCache(entry.id); }}
                        className="opacity-0 group-hover:opacity-100 transition-opacity text-[var(--color-text-muted)] hover:text-red-400 shrink-0"
                        title="Delete"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  );
                })}
              </div>
            </Card>
          </motion.div>
        )}

        {/* CTA Buttons */}
        <motion.div
          className="flex flex-col sm:flex-row justify-center gap-4 pt-8"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
        >
          <Button
            variant="primary"
            size="lg"
            onClick={handleStartAnalysis}
            icon={<Sparkles size={20} />}
            className="gradient-border"
          >
            Make Changes to Codebase
            <ArrowRight size={18} />
          </Button>

          <Button
            variant="secondary"
            size="lg"
            onClick={() => navigate("/reverse-engineer")}
            icon={<span className="text-base">🔍</span>}
          >
            Reverse Engineer from Logs
            <ArrowRight size={18} />
          </Button>
        </motion.div>
      </div>
    </Page>
  );
}
