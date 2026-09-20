/**
 * EnrichmentPanel — shows package deps, DB schemas, API endpoints, env vars
 * Displayed as tabs inside the Graph Explorer page right panel.
 */

import { useEffect, useState } from "react";
import {
  Package,
  Database,
  Globe,
  Settings2,
  ChevronDown,
  ChevronRight,
  AlertTriangle,
  Share2,
} from "lucide-react";
import { Card } from "./ui";
import {
  getPackages,
  getDbTables,
  getApiEndpoints,
  getEnvVars,
  type PackagesData,
  type DbTablesData,
  type ApiEndpointsData,
  type EnvVarsData,
} from "../api";

// ── helpers ──────────────────────────────────────────────────────────────────

const METHOD_COLORS: Record<string, string> = {
  GET: "text-emerald-400",
  POST: "text-blue-400",
  PUT: "text-amber-400",
  PATCH: "text-orange-400",
  DELETE: "text-red-400",
};

function SectionHeader({
  icon,
  label,
  count,
  open,
  onToggle,
}: {
  icon: React.ReactNode;
  label: string;
  count: number;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      onClick={onToggle}
      className="w-full flex items-center justify-between py-2 px-1
        text-sm font-medium text-[var(--color-text-primary)]
        hover:text-[var(--color-accent)] transition-colors"
    >
      <span className="flex items-center gap-2">
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        {icon}
        {label}
        <span className="text-[var(--color-text-muted)] font-normal text-xs">
          ({count})
        </span>
      </span>
    </button>
  );
}

// ── tab: packages ─────────────────────────────────────────────────────────────

function PackagesTab({ data }: { data: PackagesData | null }) {
  const [open, setOpen] = useState<Record<string, boolean>>({});

  if (!data) return <Spinner />;

  const toggle = (k: string) => setOpen((p) => ({ ...p, [k]: !p[k] }));

  return (
    <div className="space-y-1">
      {/* Shared packages banner */}
      {data.shared_packages.length > 0 && (
        <div className="mb-3 p-2 rounded bg-amber-950/30 border border-amber-800/40">
          <div className="flex items-center gap-1.5 text-amber-400 text-xs font-medium mb-1">
            <Share2 size={12} />
            {data.shared_packages.length} shared package(s)
          </div>
          <div className="space-y-1">
            {data.shared_packages.map((s) => (
              <div key={s.package} className="text-xs text-[var(--color-text-secondary)]">
                <span className="font-mono text-amber-300">{s.package}</span>
                <span className="text-[var(--color-text-muted)]">
                  {" "}in {s.used_by.join(", ")}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {Object.entries(data.by_service).map(([svc, pkgs]) => (
        <div key={svc}>
          <SectionHeader
            icon={<Package size={13} />}
            label={svc}
            count={pkgs.runtime.length}
            open={!!open[svc]}
            onToggle={() => toggle(svc)}
          />
          {open[svc] && (
            <div className="ml-5 mb-2 space-y-1">
              {pkgs.runtime.map((p) => (
                <div key={p.package} className="flex items-center justify-between">
                  <span className="text-xs font-mono text-[var(--color-text-secondary)]">
                    {p.package}
                  </span>
                  <span className="text-[10px] text-[var(--color-text-muted)]">
                    {p.version}
                  </span>
                </div>
              ))}
              {pkgs.dev.length > 0 && (
                <div className="text-[10px] text-[var(--color-text-muted)] pt-1">
                  +{pkgs.dev.length} dev dep(s)
                </div>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ── tab: db tables ────────────────────────────────────────────────────────────

function DbTablesTab({ data }: { data: DbTablesData | null }) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const toggle = (k: string) => setOpen((p) => ({ ...p, [k]: !p[k] }));

  if (!data) return <Spinner />;

  return (
    <div className="space-y-1">
      {Object.entries(data.by_service).map(([svc, tables]) => (
        <div key={svc}>
          <SectionHeader
            icon={<Database size={13} />}
            label={svc}
            count={tables.length}
            open={!!open[svc]}
            onToggle={() => toggle(svc)}
          />
          {open[svc] && (
            <div className="ml-5 mb-2 space-y-1">
              {tables.map((tbl) => (
                <div
                  key={tbl}
                  className="text-xs font-mono text-[var(--color-text-secondary)]
                    flex items-center gap-1.5"
                >
                  <Database size={10} className="text-[var(--color-text-muted)] shrink-0" />
                  {tbl}
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ── tab: api endpoints ────────────────────────────────────────────────────────

function ApiEndpointsTab({ data }: { data: ApiEndpointsData | null }) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const toggle = (k: string) => setOpen((p) => ({ ...p, [k]: !p[k] }));

  if (!data) return <Spinner />;

  return (
    <div className="space-y-1">
      {Object.entries(data.by_service).map(([svc, eps]) => (
        <div key={svc}>
          <SectionHeader
            icon={<Globe size={13} />}
            label={svc}
            count={eps.length}
            open={!!open[svc]}
            onToggle={() => toggle(svc)}
          />
          {open[svc] && (
            <div className="ml-5 mb-2 space-y-1">
              {eps.map((ep) => (
                <div key={`${ep.method}:${ep.path}`} className="flex items-baseline gap-2">
                  <span
                    className={`text-[10px] font-mono font-bold w-10 shrink-0
                      ${METHOD_COLORS[ep.method] ?? "text-[var(--color-text-muted)]"}`}
                  >
                    {ep.method}
                  </span>
                  <span className="text-xs font-mono text-[var(--color-text-secondary)] truncate">
                    {ep.path}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ── tab: env vars ─────────────────────────────────────────────────────────────

function EnvVarsTab({ data }: { data: EnvVarsData | null }) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const toggle = (k: string) => setOpen((p) => ({ ...p, [k]: !p[k] }));

  if (!data) return <Spinner />;

  return (
    <div className="space-y-1">
      {/* Shared env vars banner */}
      {data.shared_vars.length > 0 && (
        <div className="mb-3 p-2 rounded bg-blue-950/30 border border-blue-800/40">
          <div className="flex items-center gap-1.5 text-blue-400 text-xs font-medium mb-1">
            <Share2 size={12} />
            {data.shared_vars.length} var(s) shared across services
          </div>
          <div className="space-y-1">
            {data.shared_vars.map((s) => (
              <div key={s.env_var} className="text-xs text-[var(--color-text-secondary)]">
                <span className="font-mono text-blue-300">{s.env_var}</span>
                <span className="text-[var(--color-text-muted)]">
                  {" "}in {s.used_by.join(", ")}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {Object.entries(data.by_service).map(([svc, vars]) => (
        <div key={svc}>
          <SectionHeader
            icon={<Settings2 size={13} />}
            label={svc}
            count={vars.length}
            open={!!open[svc]}
            onToggle={() => toggle(svc)}
          />
          {open[svc] && (
            <div className="ml-5 mb-2 space-y-1">
              {vars.map((v) => (
                <div key={v} className="text-xs font-mono text-[var(--color-text-secondary)]">
                  {v}
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ── spinner ───────────────────────────────────────────────────────────────────

function Spinner() {
  return (
    <div className="flex justify-center py-8">
      <div className="w-5 h-5 border-2 border-[var(--color-accent)] border-t-transparent rounded-full animate-spin" />
    </div>
  );
}

// ── main component ────────────────────────────────────────────────────────────

const TABS = [
  { id: "packages",  label: "Packages",  icon: <Package  size={13} /> },
  { id: "db",        label: "DB Tables", icon: <Database size={13} /> },
  { id: "api",       label: "Endpoints", icon: <Globe    size={13} /> },
  { id: "env",       label: "Env Vars",  icon: <Settings2 size={13} /> },
] as const;

type TabId = (typeof TABS)[number]["id"];

export default function EnrichmentPanel() {
  const [activeTab, setActiveTab] = useState<TabId>("packages");
  const [packages,  setPackages]  = useState<PackagesData | null>(null);
  const [dbTables,  setDbTables]  = useState<DbTablesData | null>(null);
  const [endpoints, setEndpoints] = useState<ApiEndpointsData | null>(null);
  const [envVars,   setEnvVars]   = useState<EnvVarsData | null>(null);
  const [error,     setError]     = useState<string | null>(null);

  // Load all 4 in parallel on mount
  useEffect(() => {
    Promise.all([
      getPackages(),
      getDbTables(),
      getApiEndpoints(),
      getEnvVars(),
    ])
      .then(([pkgs, dbt, eps, evs]) => {
        setPackages(pkgs);
        setDbTables(dbt);
        setEndpoints(eps);
        setEnvVars(evs);
      })
      .catch((e) => setError(String(e)));
  }, []);

  if (error) {
    return (
      <Card className="h-full flex flex-col items-center justify-center text-center p-6">
        <AlertTriangle size={24} className="text-amber-400 mb-3" />
        <p className="text-xs text-[var(--color-text-muted)]">{error}</p>
        <p className="text-xs text-[var(--color-text-muted)] mt-1">
          Enrichment data may not be loaded yet. Restart the server.
        </p>
      </Card>
    );
  }

  const tabCount: Record<TabId, number> = {
    packages:  packages  ? Object.keys(packages.by_service).length  : 0,
    db:        dbTables  ? Object.values(dbTables.by_service).flat().length : 0,
    api:       endpoints ? endpoints.total_endpoints : 0,
    env:       envVars   ? envVars.total_entries     : 0,
  };

  return (
    <Card className="h-full flex flex-col p-0 overflow-hidden">
      {/* Tab bar */}
      <div className="flex border-b border-[var(--color-border)] shrink-0">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            className={`flex-1 flex flex-col items-center py-2 gap-0.5 text-[10px]
              border-b-2 transition-colors
              ${activeTab === t.id
                ? "border-[var(--color-accent)] text-[var(--color-accent)]"
                : "border-transparent text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]"
              }`}
          >
            {t.icon}
            <span>{t.label}</span>
            {tabCount[t.id] > 0 && (
              <span className="text-[9px] text-[var(--color-text-muted)]">
                {tabCount[t.id]}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-3">
        {activeTab === "packages"  && <PackagesTab   data={packages}  />}
        {activeTab === "db"        && <DbTablesTab   data={dbTables}  />}
        {activeTab === "api"       && <ApiEndpointsTab data={endpoints} />}
        {activeTab === "env"       && <EnvVarsTab    data={envVars}   />}
      </div>
    </Card>
  );
}
