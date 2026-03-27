export default function Header({ activePage, setActivePage, health, readiness, onRefresh, isRefreshing }) {
  const pages = [
    { id: "builder", label: "Workflow Builder" },
    { id: "executions", label: "Execution Dashboard" },
    { id: "logs", label: "Logs View" },
    { id: "workers", label: "Worker Monitor" }
  ];
  const platformStatus = readiness?.status || health?.status || "unknown";

  return (
    <header className="shell-header">
      <div>
        <p className="eyebrow">Distributed Workflow & Job Processing Engine | Created by Anish Kumar</p>
        <h1>DevFlow</h1>
        <div className="header-meta">
          <span className={`status-pill ${platformStatus === "ok" ? "success" : "retrying"}`}>{platformStatus}</span>
          <span className="meta-chip">{health?.environment || "environment unknown"}</span>
          <span className="meta-chip">v{health?.version || "n/a"}</span>
        </div>
      </div>
      <div className="header-actions">
        <nav className="nav-tabs">
          {pages.map((page) => (
            <button
              key={page.id}
              className={page.id === activePage ? "tab active" : "tab"}
              onClick={() => setActivePage(page.id)}
            >
              {page.label}
            </button>
          ))}
        </nav>
        <button className="secondary-button" onClick={onRefresh} disabled={isRefreshing}>
          {isRefreshing ? "Refreshing..." : "Refresh Runtime"}
        </button>
      </div>
    </header>
  );
}