export default function TaskGraph({ tasks }) {
  if (!tasks?.length) {
    return <div className="empty-state">No tasks to display.</div>;
  }

  return (
    <div className="task-graph">
      {tasks.map((task) => (
        <div key={task.id || task.name} className="task-node">
          <div className="task-node-header">
            <strong>{task.task_name || task.name}</strong>
            <span className={`status-pill ${task.status || "pending"}`}>{task.status || "draft"}</span>
          </div>
          <p>Dependencies: {(task.dependencies || []).join(", ") || "None"}</p>
          {task.retries !== undefined ? <p>Retries: {task.retries}</p> : null}
          {task.worker_id ? <p>Worker: {task.worker_id}</p> : null}
          {task.started_at ? <p>Started: {new Date(task.started_at).toLocaleString()}</p> : null}
          {task.finished_at ? <p>Finished: {new Date(task.finished_at).toLocaleString()}</p> : null}
          {task.error_message ? <p className="error-text">{task.error_message}</p> : null}
        </div>
      ))}
    </div>
  );
}
