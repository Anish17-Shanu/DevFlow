import TaskGraph from "../components/TaskGraph";

export default function ExecutionDashboardPage({ execution, tasks, workflows, queue, workers }) {
  const workflow = workflows.find((item) => item.id === execution?.workflow_id);
  const taskTotals = tasks.reduce(
    (summary, task) => {
      summary.total += 1;
      summary[task.status] = (summary[task.status] || 0) + 1;
      return summary;
    },
    { total: 0, pending: 0, queued: 0, running: 0, success: 0, failed: 0, retrying: 0 }
  );

  return (
    <section className="page-grid">
      <div className="panel">
        <div className="panel-heading">
          <h2>Execution overview</h2>
          <p>Live runtime state for the selected workflow execution.</p>
        </div>
        {execution ? (
          <div className="detail-grid">
            <div>
              <span className="detail-label">Workflow</span>
              <strong>{workflow?.name || execution.workflow_id}</strong>
            </div>
            <div>
              <span className="detail-label">Status</span>
              <strong className={`status-pill ${execution.status}`}>{execution.status}</strong>
            </div>
            <div>
              <span className="detail-label">Started</span>
              <strong>{execution.started_at ? new Date(execution.started_at).toLocaleString() : "Not started"}</strong>
            </div>
            <div>
              <span className="detail-label">Finished</span>
              <strong>{execution.finished_at ? new Date(execution.finished_at).toLocaleString() : "In progress"}</strong>
            </div>
          </div>
        ) : (
          <div className="empty-state">Run a workflow to inspect execution state.</div>
        )}
      </div>

      <div className="stats-grid">
        <div className="stat-card accent-blue">
          <span>Tasks</span>
          <strong>{taskTotals.total}</strong>
          <small>{taskTotals.success} successful</small>
        </div>
        <div className="stat-card accent-amber">
          <span>Active</span>
          <strong>{taskTotals.running + taskTotals.queued + taskTotals.retrying}</strong>
          <small>{taskTotals.retrying} retrying</small>
        </div>
        <div className="stat-card accent-teal">
          <span>Workers</span>
          <strong>{workers?.length ?? 0}</strong>
          <small>{queue?.in_flight_jobs ?? 0} in flight</small>
        </div>
        <div className="stat-card accent-green">
          <span>Queue processed</span>
          <strong>{queue?.total_processed ?? 0}</strong>
          <small>{queue?.queue_backend || "unknown"} backend</small>
        </div>
      </div>

      <div className="panel panel-wide">
        <div className="panel-heading">
          <h2>Task execution graph</h2>
          <p>Workers update task state in real time over queue-driven orchestration.</p>
        </div>
        <TaskGraph tasks={tasks} />
      </div>
    </section>
  );
}
