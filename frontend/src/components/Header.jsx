import StatusPill from "./StatusPill";

const NAV = [
  { name: "workflows", label: "Workflows", href: "#/workflows" },
  { name: "executions", label: "Executions", href: "#/executions" },
  { name: "monitor", label: "Monitor", href: "#/monitor" },
  { name: "operations", label: "Operations", href: "#/operations", adminOnly: true }
];

export default function Header({ routeName, me, health, readiness, onRefresh, isRefreshing, onLogout }) {
  const platformStatus = readiness?.status || health?.status || "unknown";
  const isAdmin = me?.role === "admin";

  return (
    <header className="shell-header">
      <div className="brand">
        <p className="eyebrow">Distributed workflow engine · built by Anish Kumar</p>
        <h1>
          <a href="#/workflows">DevFlow</a>
        </h1>
        <div className="header-meta">
          <StatusPill status={platformStatus === "ok" ? "success" : platformStatus === "degraded" ? "retrying" : "pending"} label={platformStatus} />
          <span className="meta-chip">{health?.environment || "environment unknown"}</span>
          <span className="meta-chip">v{health?.version || "—"}</span>
        </div>
      </div>
      <div className="header-actions">
        <nav className="nav-tabs" aria-label="Primary">
          {NAV.filter((item) => !item.adminOnly || isAdmin).map((item) => (
            <a
              key={item.name}
              href={item.href}
              className={item.name === routeName || (item.name === "workflows" && routeName === "builder") ? "tab active" : "tab"}
              aria-current={item.name === routeName ? "page" : undefined}
            >
              {item.label}
            </a>
          ))}
        </nav>
        <div className="header-session">
          <span className="meta-chip" title={me?.tenant_name || ""}>
            {me?.role ? `${me.role} · ${me.key_name}` : "not signed in"}
          </span>
          <button className="secondary-button" onClick={onRefresh} disabled={isRefreshing}>
            {isRefreshing ? "Refreshing…" : "Refresh"}
          </button>
          <button className="ghost-button" onClick={onLogout}>
            Sign out
          </button>
        </div>
      </div>
    </header>
  );
}
