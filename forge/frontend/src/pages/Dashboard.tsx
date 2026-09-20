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
} from "lucide-react";
import { Page, Card, StatCard, Button, Badge, StatusDot, Logo } from "../components/ui";
import HowForgeWorks from "../components/HowForgeWorks";
import { getGraphStats } from "../api";

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

  useEffect(() => {
    loadData();
  }, []);

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
          className="flex-1 min-h-0 flex flex-col"
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

        {/* CTA Button */}
        <motion.div
          className="flex justify-center pt-8"
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
        </motion.div>
      </div>
    </Page>
  );
}
