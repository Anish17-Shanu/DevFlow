import TaskGraph from "../components/TaskGraph";

export default function ExecutionDashboardPage({ execution, tasks, workflows }) {
  const workflow = workflows.find((item) => item.id === execution?.workflow_id);

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
              <strong>{execution.started_at || "Not started"}</strong>
            </div>
            <div>
              <span className="detail-label">Finished</span>
              <strong>{execution.finished_at || "In progress"}</strong>
            </div>
          </div>
        ) : (
          <div className="empty-state">Run a workflow to inspect execution state.</div>
        )}
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
