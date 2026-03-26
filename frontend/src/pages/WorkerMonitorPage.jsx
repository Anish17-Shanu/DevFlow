import StatCard from "../components/StatCard";

export default function WorkerMonitorPage({ queue, workers }) {
  return (
    <section className="page-grid">
      <div className="stats-grid">
        <StatCard label="Queued" value={queue?.queued_jobs ?? 0} />
        <StatCard label="Delayed" value={queue?.delayed_jobs ?? 0} accent="amber" />
        <StatCard label="In Flight" value={queue?.in_flight_jobs ?? 0} accent="teal" />
        <StatCard label="Processed" value={queue?.total_processed ?? 0} accent="green" />
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
                <p>Current execution: {worker.current_execution_id || "Idle"}</p>
                <p>Current task: {worker.current_task_id || "Idle"}</p>
                <p>Last seen: {worker.last_seen_at || "Unknown"}</p>
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
