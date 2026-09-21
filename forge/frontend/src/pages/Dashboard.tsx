import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  GitGraph,
  Box,
  GitBranch,
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
} from "lucide-react";
import { Page, Card, StatCard, Button, Badge, StatusDot, Logo } from "../components/ui";
import HowForgeWorks from "../components/HowForgeWorks";
import { getGraphStats, listCache, deleteCacheEntry, type CacheEntry } from "../api";

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
      <div className="grid grid-cols-4 gap-4 mb-6">
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
          <StatCard
            value={stats.packages}
            label="Packages"
            icon={<Package size={20} />}
          />
        </motion.div>
      </div>

      {/* Enrichment stats sub-row */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.28 }}
        >
          <StatCard
            value={stats.db_tables}
            label="DB Tables"
            icon={<Database size={20} />}
          />
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
        >
          <StatCard
            value={stats.api_endpoints}
            label="API Endpoints"
            icon={<Globe size={20} />}
          />
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.32 }}
        >
          <StatCard
            value={stats.env_vars}
            label="Env Vars"
            icon={<Settings2 size={20} />}
          />
        </motion.div>
      </div>

      {/* Main Content — two-column grid */}
      <div className="grid grid-cols-[1fr_360px] gap-6 flex-1 min-h-0">
        {/* LEFT: Services Table */}
        <motion.div
          className="flex flex-col min-h-0"
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

          <Card className="flex-1 overflow-hidden flex flex-col">
            {loading ? (
              <div className="flex-1 flex items-center justify-center">
                <div className="shimmer w-full h-12 rounded-lg" />
              </div>
            ) : services.length === 0 ? (
              <div className="flex-1 flex flex-col items-center justify-center text-center p-8">
                <Box size={48} className="text-[var(--color-text-muted)] mb-4 opacity-50" />
                <p className="text-[var(--color-text-muted)]">
                  No services found. Ingest a repository to get started.
                </p>
              </div>
            ) : (
              <div className="overflow-auto flex-1">
                <table className="table">
                  <thead>
                    <tr>
                      <th className="w-8"></th>
                      <th>Service</th>
                      <th className="text-right">Fns</th>
                      <th className="text-right">In</th>
                      <th className="text-right">Out</th>
                      <th className="text-right" title="npm packages"><Package size={12} className="inline" /></th>
                      <th className="text-right" title="DB tables"><Database size={12} className="inline" /></th>
                      <th className="text-right" title="API endpoints"><Globe size={12} className="inline" /></th>
                      <th className="text-right" title="Env vars"><Settings2 size={12} className="inline" /></th>
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
                        <td className="text-right font-mono text-[var(--color-text-muted)]">
                          {service.packages > 0 ? service.packages : <span className="opacity-30">—</span>}
                        </td>
                        <td className="text-right font-mono text-[var(--color-text-muted)]">
                          {service.db_tables > 0 ? service.db_tables : <span className="opacity-30">—</span>}
                        </td>
                        <td className="text-right font-mono text-[var(--color-text-muted)]">
                          {service.api_endpoints > 0 ? service.api_endpoints : <span className="opacity-30">—</span>}
                        </td>
                        <td className="text-right font-mono text-[var(--color-text-muted)]">
                          {service.env_vars > 0 ? service.env_vars : <span className="opacity-30">—</span>}
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

        {/* RIGHT: Past Requests + CTA */}
        <div className="flex flex-col gap-4 min-h-0">
          {/* Past Requests & Results panel */}
          {cacheEntries.length > 0 && (
            <motion.div
              className="flex flex-col min-h-0"
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
                <span className="text-xs text-[var(--color-text-muted)]">
                  Click to view
                </span>
              </div>

              <Card className="overflow-hidden flex-1">
                <div className="overflow-y-auto h-full divide-y divide-[var(--color-glass-border)]">
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
                        className="flex items-center gap-3 px-3 py-2.5 hover:bg-[var(--color-glass-bg)] transition-colors group cursor-pointer"
                      >
                        {/* Type badge */}
                        <span className={`text-xs font-mono font-bold w-14 shrink-0 ${typeColors[entry.pipeline_type] || "text-[var(--color-text-muted)]"}`}>
                          {typeLabels[entry.pipeline_type] || entry.pipeline_type}
                        </span>

                        {/* Label */}
                        <span className="flex-1 text-xs text-[var(--color-text-primary)] truncate group-hover:text-[var(--color-accent)] transition-colors">
                          {entry.label}
                        </span>

                        {/* Last used */}
                        <span className="text-xs text-[var(--color-text-muted)] shrink-0 flex items-center gap-1">
                          <Clock size={10} />
                          {agoStr}
                        </span>

                        {/* Arrow hint */}
                        <span className="opacity-0 group-hover:opacity-100 transition-opacity text-[var(--color-accent)] shrink-0 text-xs">
                          →
                        </span>

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
            </Button>

            <Button
              variant="secondary"
              size="lg"
              onClick={() => navigate("/reverse-engineer")}
              icon={<span className="text-base">🔍</span>}
              className="w-full"
            >
              Reverse Engineer from Logs
            </Button>
          </motion.div>
        </div>
      </div>
    </Page>
  );
}
