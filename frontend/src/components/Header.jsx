export default function Header({ activePage, setActivePage }) {
  const pages = [
    { id: "builder", label: "Workflow Builder" },
    { id: "executions", label: "Execution Dashboard" },
    { id: "logs", label: "Logs View" },
    { id: "workers", label: "Worker Monitor" }
  ];

  return (
    <header className="shell-header">
      <div>
        <p className="eyebrow">Distributed Workflow & Job Processing Engine • Created by Anish Kumar</p>
        <h1>DevFlow</h1>
      </div>
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
    </header>
  );
}
