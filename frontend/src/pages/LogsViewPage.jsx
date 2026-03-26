export default function LogsViewPage({ logs }) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Execution logs</h2>
        <p>Every state transition and worker action is persisted for auditability.</p>
      </div>
      <div className="logs-list">
        {logs.length ? (
          logs.map((log) => (
            <article key={log.id} className="log-row">
              <span className={`log-level ${log.level.toLowerCase()}`}>{log.level}</span>
              <div>
                <strong>{new Date(log.created_at).toLocaleString()}</strong>
                <p>{log.message}</p>
              </div>
            </article>
          ))
        ) : (
          <div className="empty-state">Logs will appear after a workflow is executed.</div>
        )}
      </div>
    </section>
  );
}
