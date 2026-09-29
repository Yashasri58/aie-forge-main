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
  Package,
  Globe,
  Settings2,
  ChevronDown,
  ChevronRight,
  Download,
  GitCommit,
  RotateCcw,
} from "lucide-react";
import { Page, Card, StatCard, Button, Badge, StatusDot, Logo } from "../components/ui";
import HowForgeWorks from "../components/HowForgeWorks";
import {
  getGraphStats, listCache, deleteCacheEntry,
  getServiceEnrichment, listVersions, downloadVersion, revertVersion,
  type CacheEntry, type ServiceEnrichment, type VersionEntry,
} from "../api";
import { entryToMarkdown, triggerDownload, safeFilename } from "../utils/downloadUtils";
import JSZip from "jszip";

interface ServiceOverview {
  id: string;
  name: string;
  functions: number;
  inbound: number;
  outbound: number;
  packages: number;
  db_tables: number;
  api_endpoints: number;
  env_vars: number;
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [stats, setStats] = useState({
    services: 0, symbols: 0, edges: 0,
    packages: 0, db_tables: 0, api_endpoints: 0, env_vars: 0,
  });
  const [services, setServices] = useState<ServiceOverview[]>([]);
  const [loading, setLoading] = useState(true);
  const [showHowItWorks, setShowHowItWorks] = useState(false);
  const [cacheEntries, setCacheEntries] = useState<CacheEntry[]>([]);
  const [expandedService, setExpandedService] = useState<string | null>(null);
  const [enrichmentCache, setEnrichmentCache] = useState<Record<string, ServiceEnrichment>>({});
  const [enrichmentLoading, setEnrichmentLoading] = useState<string | null>(null);
  const [versions, setVersions] = useState<VersionEntry[]>([]);
  const [revertingHash, setRevertingHash] = useState<string | null>(null);

  useEffect(() => {
    loadData();
    loadCache();
    loadVersions();
  }, []);

  async function loadCache() {
    try {
      const entries = await listCache();
      setCacheEntries(entries);
    } catch {
      // cache unavailable — not critical
    }
  }

  async function loadVersions() {
    try {
      const v = await listVersions();
      setVersions(v);
    } catch {
      // sync feature may not be enabled — not critical
    }
  }

  async function handleRevert(stateId: string, shortHash: string) {
    if (!stateId) return;
    setRevertingHash(shortHash);
    try {
      await revertVersion(stateId);
      await loadVersions(); // refresh list
    } catch (err: any) {
      console.error("Revert failed:", err.message);
    } finally {
      setRevertingHash(null);
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

      results.forEach((entry) => {
        const md = entryToMarkdown(entry);
        const filename = safeFilename(entry.label || entry.id, entry.id.slice(0, 8));
        zip.file(filename, md);
      });

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

      const res = await fetch("/graph/overview");
      const data = await res.json();

      const serviceNodes = data.nodes?.filter((n: { type: string }) => n.type === "service") || [];
      const edges = data.edges || [];

      const serviceList: ServiceOverview[] = serviceNodes.map((node: { id: string; label: string; child_count?: number; properties?: Record<string, number> }) => {
        const inbound = edges.filter((e: { target: string }) => e.target === node.id).length;
        const outbound = edges.filter((e: { source: string }) => e.source === node.id).length;
        const props = node.properties || {};
        return {
          id: node.id,
          name: node.label,
          functions: node.child_count || 0,
          inbound,
          outbound,
          packages: props.packages ?? 0,
          db_tables: props.db_tables ?? 0,
          api_endpoints: props.api_endpoints ?? 0,
          env_vars: props.env_vars ?? 0,
        };
      });

      setServices(serviceList);
    } catch (err) {
      console.error("Failed to load dashboard data:", err);
    } finally {
      setLoading(false);
    }
  }

  async function handleToggleExpand(serviceName: string) {
    if (expandedService === serviceName) {
      setExpandedService(null);
      return;
    }
    setExpandedService(serviceName);
    if (!enrichmentCache[serviceName]) {
      setEnrichmentLoading(serviceName);
      try {
        const data = await getServiceEnrichment(serviceName);
        setEnrichmentCache(prev => ({ ...prev, [serviceName]: data }));
      } catch {
        // ignore — show empty state
      } finally {
        setEnrichmentLoading(null);
      }
    }
  }

  async function handleStartAnalysis() {
    navigate(`/chat/new`);
  }

  return (
    <Page scrollable>
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

      {/* Stats Row — 4 main stats */}
      <div className="grid grid-cols-4 gap-4 mb-4">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
          <StatCard value={stats.services} label="Services" icon={<Box size={20} />} />
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}>
          <StatCard value={stats.symbols} label="Functions" icon={<GitBranch size={20} />} />
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
          <StatCard value={stats.edges} label="Connections" icon={<Zap size={20} />} />
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }}>
          <StatCard value={stats.packages} label="Packages" icon={<Package size={20} />} />
        </motion.div>
      </div>

      {/* Enrichment stats sub-row */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.28 }}>
          <StatCard value={stats.db_tables} label="DB Tables" icon={<Database size={20} />} />
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
          <StatCard value={stats.api_endpoints} label="API Endpoints" icon={<Globe size={20} />} />
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.32 }}>
          <StatCard value={stats.env_vars} label="Env Vars" icon={<Settings2 size={20} />} />
        </motion.div>
      </div>

      {/* Main Content — two-column grid */}
      <div className="grid grid-cols-[1fr_360px] gap-6">
        {/* LEFT: Services Table */}
        <motion.div
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
              <div className="overflow-auto" style={{ maxHeight: "420px" }}>
                <table className="table w-full text-sm">
                  <thead>
                    <tr>
                      <th className="w-8"></th>
                      <th className="w-2"></th>
                      <th className="text-left">Service</th>
                      <th className="w-16 text-right">Fns</th>
                      <th className="w-16 text-right">In</th>
                      <th className="w-16 text-right">Out</th>
                      <th className="w-16 text-right">
                        <span title="npm packages" className="flex items-center justify-end gap-1">
                          <Package size={11} className="opacity-60" /> Pkgs
                        </span>
                      </th>
                      <th className="w-16 text-right">
                        <span title="DB tables" className="flex items-center justify-end gap-1">
                          <Database size={11} className="opacity-60" /> DBs
                        </span>
                      </th>
                      <th className="w-16 text-right">
                        <span title="API endpoints" className="flex items-center justify-end gap-1">
                          <Globe size={11} className="opacity-60" /> APIs
                        </span>
                      </th>
                      <th className="w-16 text-right">
                        <span title="Env vars" className="flex items-center justify-end gap-1">
                          <Settings2 size={11} className="opacity-60" /> Env
                        </span>
                      </th>
                      <th className="w-8"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {services.map((service, i) => {
                      const isExpanded = expandedService === service.name;
                      const enrichment = enrichmentCache[service.name];
                      const isLoading = enrichmentLoading === service.name;
                      return (
                        <>
                          <motion.tr
                            key={service.id}
                            initial={{ opacity: 0, x: -20 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ delay: 0.04 * i }}
                            className={`group cursor-pointer select-none ${isExpanded ? "bg-[var(--color-glass-bg)]" : ""}`}
                            onClick={() => handleToggleExpand(service.name)}
                          >
                            {/* chevron */}
                            <td className="w-8 text-center">
                              <span className="text-[var(--color-text-muted)] inline-flex items-center">
                                {isExpanded
                                  ? <ChevronDown size={14} />
                                  : <ChevronRight size={14} />}
                              </span>
                            </td>
                            {/* colour bar */}
                            <td className="w-2 p-0">
                              <div
                                className="w-1 h-8 rounded-full"
                                style={{ background: `hsl(${(i * 45) % 360}, 70%, 60%)` }}
                              />
                            </td>
                            <td>
                              <span className={`font-medium transition-colors ${isExpanded ? "text-[var(--color-accent)]" : "text-[var(--color-text-primary)] group-hover:text-[var(--color-accent)]"}`}>
                                {service.name}
                              </span>
                            </td>
                            <td className="w-16 text-right font-mono">{service.functions}</td>
                            <td className="w-16 text-right font-mono text-[var(--color-success)]">↓ {service.inbound}</td>
                            <td className="w-16 text-right font-mono text-[var(--color-accent)]">↑ {service.outbound}</td>
                            <td className="w-16 text-right font-mono text-[var(--color-text-muted)]">
                              {service.packages > 0 ? service.packages : <span className="opacity-30">—</span>}
                            </td>
                            <td className="w-16 text-right font-mono text-[var(--color-text-muted)]">
                              {service.db_tables > 0 ? service.db_tables : <span className="opacity-30">—</span>}
                            </td>
                            <td className="w-16 text-right font-mono text-[var(--color-text-muted)]">
                              {service.api_endpoints > 0 ? service.api_endpoints : <span className="opacity-30">—</span>}
                            </td>
                            <td className="w-16 text-right font-mono text-[var(--color-text-muted)]">
                              {service.env_vars > 0 ? service.env_vars : <span className="opacity-30">—</span>}
                            </td>
                            <td className="w-8">
                              <button
                                className="opacity-0 group-hover:opacity-100 transition-opacity text-[var(--color-text-muted)] hover:text-[var(--color-accent)]"
                                onClick={(e) => { e.stopPropagation(); navigate(`/explore?focus=${service.id}`); }}
                                title="View in graph"
                              >
                                <ExternalLink size={13} />
                              </button>
                            </td>
                          </motion.tr>

                          {/* Expand detail row */}
                          {isExpanded && (
                            <tr key={`${service.id}-detail`} className="bg-[var(--color-glass-bg)]">
                              <td colSpan={11} className="px-10 pb-4 pt-2">
                                {isLoading ? (
                                  <div className="text-xs text-[var(--color-text-muted)] py-2 animate-pulse">Loading enrichment…</div>
                                ) : enrichment ? (
                                  <div className="grid grid-cols-2 gap-x-8 gap-y-3 text-xs">
                                    {/* Packages */}
                                    {enrichment.packages.length > 0 && (
                                      <div>
                                        <div className="flex items-center gap-1 text-[var(--color-text-muted)] mb-1 font-semibold uppercase tracking-wide" style={{ fontSize: "10px" }}>
                                          <Package size={10} /> npm packages ({enrichment.packages.length})
                                        </div>
                                        <div className="flex flex-wrap gap-1">
                                          {enrichment.packages.map(p => (
                                            <span key={p.name} className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-[var(--color-glass-border)] text-[var(--color-text-primary)]">
                                              {p.name}
                                              {p.version && <span className="text-[var(--color-text-muted)]">@{p.version}</span>}
                                              {p.dep_type === "dev" && <span className="text-yellow-500 opacity-70">dev</span>}
                                            </span>
                                          ))}
                                        </div>
                                      </div>
                                    )}

                                    {/* DB Tables */}
                                    {enrichment.db_tables.length > 0 && (
                                      <div>
                                        <div className="flex items-center gap-1 text-[var(--color-text-muted)] mb-1 font-semibold uppercase tracking-wide" style={{ fontSize: "10px" }}>
                                          <Database size={10} /> DB tables ({enrichment.db_tables.length})
                                        </div>
                                        <div className="flex flex-wrap gap-1">
                                          {enrichment.db_tables.map(t => (
                                            <span key={t} className="px-2 py-0.5 rounded bg-[var(--color-glass-border)] text-[var(--color-text-primary)]">{t}</span>
                                          ))}
                                        </div>
                                      </div>
                                    )}

                                    {/* API Endpoints */}
                                    {enrichment.api_endpoints.length > 0 && (
                                      <div className="col-span-2">
                                        <div className="flex items-center gap-1 text-[var(--color-text-muted)] mb-1 font-semibold uppercase tracking-wide" style={{ fontSize: "10px" }}>
                                          <Globe size={10} /> API endpoints ({enrichment.api_endpoints.length})
                                        </div>
                                        <div className="flex flex-wrap gap-1">
                                          {enrichment.api_endpoints.map(ep => (
                                            <span key={`${ep.method}:${ep.path}`} className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-[var(--color-glass-border)] text-[var(--color-text-primary)] font-mono">
                                              <span className={`font-bold text-[10px] ${
                                                ep.method === "GET" ? "text-green-400" :
                                                ep.method === "POST" ? "text-blue-400" :
                                                ep.method === "PUT" ? "text-yellow-400" :
                                                ep.method === "DELETE" ? "text-red-400" :
                                                "text-[var(--color-text-muted)]"
                                              }`}>{ep.method}</span>
                                              {ep.path}
                                            </span>
                                          ))}
                                        </div>
                                      </div>
                                    )}

                                    {/* Env vars */}
                                    {enrichment.env_vars.length > 0 && (
                                      <div className="col-span-2">
                                        <div className="flex items-center gap-1 text-[var(--color-text-muted)] mb-1 font-semibold uppercase tracking-wide" style={{ fontSize: "10px" }}>
                                          <Settings2 size={10} /> env vars ({enrichment.env_vars.length})
                                        </div>
                                        <div className="flex flex-wrap gap-1">
                                          {enrichment.env_vars.map(v => (
                                            <span key={v} className="px-2 py-0.5 rounded bg-[var(--color-glass-border)] text-[var(--color-text-primary)] font-mono">{v}</span>
                                          ))}
                                        </div>
                                      </div>
                                    )}

                                    {enrichment.packages.length === 0 && enrichment.db_tables.length === 0 &&
                                     enrichment.api_endpoints.length === 0 && enrichment.env_vars.length === 0 && (
                                      <div className="col-span-2 text-[var(--color-text-muted)] py-1">No enrichment data for this service.</div>
                                    )}
                                  </div>
                                ) : (
                                  <div className="text-xs text-[var(--color-text-muted)] py-1">No enrichment data available.</div>
                                )}
                              </td>
                            </tr>
                          )}
                        </>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </motion.div>

        {/* RIGHT column: History + CTAs */}
        <div className="flex flex-col gap-4">

          {/* Past Requests & Results */}
          {cacheEntries.length > 0 && (
            <motion.div
              className="flex flex-col"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.35 }}
            >
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Database size={16} className="text-[var(--color-accent)]" />
                  <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">
                    Past Requests & Results
                  </h2>
                  <Badge variant="accent">{cacheEntries.length}</Badge>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={handleDownloadAll}
                    className="flex items-center gap-1 px-2 py-1 rounded text-xs text-[var(--color-text-muted)] hover:text-[var(--color-accent)] hover:bg-[var(--color-glass-bg)] transition-all"
                    title="Download all as ZIP"
                  >
                    <Download size={12} />
                    All
                  </button>
                  <span className="text-xs text-[var(--color-text-muted)]">Click to view</span>
                </div>
              </div>

              <Card className="overflow-hidden">
                {/* Scrollable list */}
                <div className="overflow-y-auto divide-y divide-[var(--color-glass-border)]" style={{ maxHeight: "380px" }}>
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
                    const agoStr = ago < 60 ? `${ago}m ago` : `${Math.round(ago / 60)}h ago`;

                    return (
                      <div
                        key={entry.id}
                        onClick={() => navigate(`/history/${entry.id}`)}
                        className="flex items-center gap-3 px-3 py-2.5 hover:bg-[var(--color-glass-bg)] transition-colors group cursor-pointer"
                      >
                        {/* Type badge */}
                        <span className={`text-xs font-mono font-bold w-14 shrink-0 ${typeColors[entry.pipeline_type] || "text-[var(--color-text-muted)]"}`}>
                          {typeLabels[entry.pipeline_type] || entry.pipeline_type}
                        </span>

                        {/* Label */}
                        <span className="flex-1 text-xs text-[var(--color-text-primary)] truncate group-hover:text-[var(--color-accent)] transition-colors">
                          {entry.label?.replace(/^\[REJECTED\]\s*/, "") ?? ""}
                        </span>
                        {entry.label?.startsWith("[REJECTED]") && (
                          <span className="shrink-0 px-1.5 py-0.5 rounded text-[10px] font-bold bg-[var(--color-error-subtle)] text-[var(--color-error)]">
                            REJECTED
                          </span>
                        )}

                        {/* Last used */}
                        <span className="text-xs text-[var(--color-text-muted)] shrink-0 flex items-center gap-1">
                          <Clock size={10} />
                          {agoStr}
                        </span>

                        {/* Arrow */}
                        <span className="opacity-0 group-hover:opacity-100 transition-opacity text-[var(--color-accent)] shrink-0 text-xs">→</span>

                        {/* Download */}
                        <button
                          onClick={(e) => { e.stopPropagation(); handleDownloadCache(entry.id, entry.label); }}
                          className="opacity-0 group-hover:opacity-100 transition-opacity text-[var(--color-text-muted)] hover:text-[var(--color-accent)] shrink-0"
                          title="Download"
                        >
                          <Download size={12} />
                        </button>

                        {/* Delete */}
                        <button
                          onClick={(e) => { e.stopPropagation(); handleDeleteCache(entry.id); }}
                          className="opacity-0 group-hover:opacity-100 transition-opacity text-[var(--color-text-muted)] hover:text-red-400 shrink-0"
                          title="Delete"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    );
                  })}
                </div>
              </Card>
            </motion.div>
          )}

          {/* Version History */}
          {versions.length > 0 && (
            <motion.div
              className="flex flex-col"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.38 }}
            >
              <div className="flex items-center gap-2 mb-3">
                <GitCommit size={16} className="text-[var(--color-accent)]" />
                <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">
                  AI Commits
                </h2>
                <Badge variant="accent">{versions.length}</Badge>
              </div>

              <Card className="overflow-hidden">
                <div className="overflow-y-scroll divide-y divide-[var(--color-glass-border)]" style={{ maxHeight: "240px" }}>
                  {versions.map((v) => {
                    const date = new Date(v.timestamp);
                    const ago = Math.round((Date.now() - date.getTime()) / 60000);
                    const agoStr = ago < 60 ? `${ago}m ago` : `${Math.round(ago / 60)}h ago`;
                    const isReverting = revertingHash === v.short_hash;

                    return (
                      <div key={v.commit_hash} className="flex items-start gap-2 px-3 py-2.5 hover:bg-[var(--color-glass-bg)] group transition-colors">
                        {/* hash badge */}
                        <span className="font-mono text-[10px] text-[var(--color-accent)] bg-[var(--color-glass-bg)] px-1.5 py-0.5 rounded shrink-0 mt-0.5">
                          {v.short_hash}
                        </span>

                        {/* message + files */}
                        <div className="flex-1 min-w-0">
                          <p className="text-xs text-[var(--color-text-primary)] truncate">
                            {v.message.replace(/^AI codegen:\s*/i, "")}
                          </p>
                          <p className="text-[10px] text-[var(--color-text-muted)] mt-0.5">
                            {v.changed_files.length} file{v.changed_files.length !== 1 ? "s" : ""} · {agoStr}
                          </p>
                        </div>

                        {/* actions */}
                        <div className="flex items-center gap-1 shrink-0">
                          <button
                            onClick={() => downloadVersion(v.commit_hash, v.short_hash)}
                            className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded hover:bg-[var(--color-glass-bg)] text-[var(--color-text-muted)] hover:text-[var(--color-accent)]"
                            title="Download zip at this commit"
                          >
                            <Download size={13} />
                          </button>
                          <button
                            onClick={() => handleRevert(v.state_id, v.short_hash)}
                            disabled={isReverting}
                            className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded hover:bg-[var(--color-glass-bg)] text-[var(--color-text-muted)] hover:text-yellow-400 disabled:opacity-50"
                            title="Revert this commit"
                          >
                            <RotateCcw size={13} className={isReverting ? "animate-spin" : ""} />
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </Card>
            </motion.div>
          )}

          {/* CTA Buttons */}
          <motion.div
            className="flex flex-col gap-3 mt-auto"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 }}
          >
            <Button
              variant="primary"
              size="lg"
              onClick={handleStartAnalysis}
              icon={<Sparkles size={18} />}
              className="gradient-border w-full"
            >
              Make Changes to Codebase
              <ArrowRight size={16} />
            </Button>

            <Button
              variant="secondary"
              size="lg"
              onClick={() => navigate("/reverse-engineer")}
              icon={<span className="text-base">🔍</span>}
              className="w-full"
            >
              Reverse Engineer from Logs
              <ArrowRight size={16} />
            </Button>
          </motion.div>
        </div>
      </div>
    </Page>
  );
}
