import StatCard from "../components/StatCard";

export default function WorkerMonitorPage({ queue, workers, readiness }) {
  return (
    <section className="page-grid">
      <div className="stats-grid">
        <StatCard label="Queued" value={queue?.queued_jobs ?? 0} />
        <StatCard label="Delayed" value={queue?.delayed_jobs ?? 0} accent="amber" />
        <StatCard label="In Flight" value={queue?.in_flight_jobs ?? 0} accent="teal" />
        <StatCard label="Processed" value={queue?.total_processed ?? 0} accent="green" />
      </div>
      <div className="panel">
        <div className="panel-heading">
          <h2>Platform readiness</h2>
          <p>Operational snapshot for database, workers, and queue durability.</p>
        </div>
        <div className="detail-grid">
          <div>
            <span className="detail-label">Readiness</span>
            <strong className={`status-pill ${readiness?.status === "ok" ? "success" : "retrying"}`}>
              {readiness?.status || "unknown"}
            </strong>
          </div>
          <div>
            <span className="detail-label">Database</span>
            <strong>{readiness?.database || "unknown"}</strong>
          </div>
          <div>
            <span className="detail-label">Workers</span>
            <strong>{readiness?.workers || "unknown"}</strong>
          </div>
          <div>
            <span className="detail-label">Queue durability</span>
            <strong>{queue?.is_durable ? "durable" : "ephemeral"}</strong>
          </div>
        </div>
      </div>
      <div className="panel panel-wide">
        <div className="panel-heading">
          <h2>Worker fleet</h2>
          <p>Stateless workers polling the queue and executing tasks concurrently.</p>
        </div>
        <div className="worker-list">
          {workers.length ? (
            workers.map((worker) => (
              <article key={worker.worker_id} className="worker-card">
                <div className="task-node-header">
                  <strong>{worker.worker_id}</strong>
                  <span className={`status-pill ${worker.state}`}>{worker.state}</span>
                </div>
                <p>Processed jobs: {worker.processed_jobs}</p>
                <p>Failed jobs: {worker.failed_jobs ?? 0}</p>
                <p>Current execution: {worker.current_execution_id || "Idle"}</p>
                <p>Current task: {worker.current_task_id || "Idle"}</p>
                <p>Last seen: {worker.last_seen_at ? new Date(worker.last_seen_at).toLocaleString() : "Unknown"}</p>
                {worker.last_error ? <p className="error-text">{worker.last_error}</p> : null}
              </article>
            ))
          ) : (
            <div className="empty-state">No workers registered.</div>
          )}
        </div>
      </div>
    </section>
  );
}
