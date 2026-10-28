import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import ConfirmDialog from "../components/ConfirmDialog";
import StatusPill from "../components/StatusPill";
import TaskGraph from "../components/TaskGraph";
import { formatDate, formatDuration, formatRelative, shortId } from "../lib/format";
import { pathFor } from "../lib/router";
import { api } from "../services/api";

const LEVELS = ["", "INFO", "WARNING", "ERROR"];

export default function ExecutionDetailPage({ executionId, me, notify }) {
  const [execution, setExecution] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [logs, setLogs] = useState([]);
  const [selectedTask, setSelectedTask] = useState("");
  const [level, setLevel] = useState("");
  const [autoScroll, setAutoScroll] = useState(true);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [streamState, setStreamState] = useState("connecting");
  const [action, setAction] = useState("");
  const [pendingCancel, setPendingCancel] = useState(false);
  const logEndRef = useRef(null);

  const canOperate = me?.role === "operator" || me?.role === "admin";

  const load = useCallback(async () => {
    setError("");
    try {
      const [executionData, taskData, logData] = await Promise.all([
        api.getExecution(executionId),
        api.getExecutionTasks(executionId),
        api.getExecutionLogs(executionId, { limit: 1000 })
      ]);
      setExecution(executionData);
      setTasks(taskData || []);
      setLogs(logData.items || []);
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  }, [executionId]);

  useEffect(() => {
    setLoading(true);
    setExecution(null);
    setTasks([]);
    setLogs([]);
    setSelectedTask("");
    load();
  }, [load]);

  useEffect(() => {
    const interval = setInterval(() => {
      if (document.visibilityState === "visible") load();
    }, 3000);
    return () => clearInterval(interval);
  }, [load]);

  useEffect(() => {
    let disposed = false;
    let socket;
    let retryTimer;

    const connect = () => {
      setStreamState("connecting");
      try {
        socket = api.executionSocket(executionId);
      } catch {
        setStreamState("offline");
        return;
      }
      socket.onopen = () => {
        setStreamState("live");
        socket.send("subscribe");
      };
      socket.onmessage = () => load();
      socket.onclose = () => {
        if (disposed) return;
        setStreamState("polling");
        retryTimer = setTimeout(connect, 5000);
      };
      socket.onerror = () => socket.close();
    };

    connect();
    return () => {
      disposed = true;
      clearTimeout(retryTimer);
      socket?.close();
    };
  }, [executionId, load]);

  useEffect(() => {
    if (autoScroll) logEndRef.current?.scrollIntoView({ block: "end" });
  }, [logs, autoScroll]);

  const filteredLogs = useMemo(
    () => (level ? logs.filter((log) => log.level === level) : logs),
    [logs, level]
  );

  const summary = useMemo(() => {
    return tasks.reduce(
      (accumulator, task) => {
        accumulator.total += 1;
        accumulator[task.status] = (accumulator[task.status] || 0) + 1;
        return accumulator;
      },
      { total: 0, success: 0, failed: 0, running: 0, queued: 0, pending: 0, retrying: 0, cancelled: 0, skipped: 0 }
    );
  }, [tasks]);

  const currentTask = tasks.find((task) => task.task_name === selectedTask) || null;

  const doAction = async (label, promise) => {
    setAction(label);
    try {
      await promise;
      notify(`${label} requested.`, "success");
      await load();
    } catch (actionError) {
      notify(actionError.message, "error");
    } finally {
      setAction("");
    }
  };

  const cancel = async () => {
    setPendingCancel(false);
    await doAction("Cancel", api.cancelExecution(executionId));
  };

  const retryExecution = async () => {
    setAction("Retry execution");
    try {
      const copy = await api.retryExecution(executionId);
      notify("Retry started.", "success");
      window.location.hash = `#/${pathFor.execution(copy.id)}`;
    } catch (retryError) {
      notify(retryError.message, "error");
    } finally {
      setAction("");
    }
  };

  if (loading && !execution) {
    return <div className="empty-state">Loading execution…</div>;
  }

  if (error && !execution) {
    return (
      <section className="page-stack">
        <div className="error-text" role="alert">
          {error}
        </div>
        <a className="button-link" href="#/executions">
          Back to executions
        </a>
      </section>
    );
  }

  if (!execution) return null;

  const isTerminal = ["success", "failed", "cancelled"].includes(execution.status);

  return (
    <section className="page-stack">
      <div className="page-heading">
        <div>
          <p className="eyebrow">
            Execution <code>{shortId(execution.id)}</code> · revision r{execution.revision}
          </p>
          <h2>{execution.workflow_name || "Workflow execution"}</h2>
          <div className="header-meta">
            <StatusPill status={execution.status} />
            <span className={`stream-state ${streamState}`}>● {streamState}</span>
            <span className="meta-chip">Triggered by {execution.triggered_by}</span>
            <span className="meta-chip">Started {formatRelative(execution.started_at)}</span>
            <span className="meta-chip">Took {formatDuration(execution.started_at, execution.finished_at)}</span>
          </div>
        </div>
        <div className="button-row">
          <a className="ghost-button" href={`#/${pathFor.builder(execution.workflow_id)}`}>
            View workflow
          </a>
          {canOperate && !isTerminal ? (
            <button className="danger-text-button" onClick={() => setPendingCancel(true)} disabled={Boolean(action)}>
              Cancel execution
            </button>
          ) : null}
          {canOperate && isTerminal ? (
            <button className="secondary-button" onClick={retryExecution} disabled={Boolean(action)}>
              Retry execution
            </button>
          ) : null}
        </div>
      </div>

      {error ? (
        <div className="error-text" role="alert">
          {error}
        </div>
      ) : null}

      <div className="stats-grid">
        <div className="stat-card accent-blue">
          <span>Tasks</span>
          <strong>
            {summary.success + summary.skipped}/{summary.total}
          </strong>
          <small>{summary.failed} failed · {summary.cancelled} cancelled</small>
        </div>
        <div className="stat-card accent-amber">
          <span>Active</span>
          <strong>{summary.running + summary.queued + summary.retrying}</strong>
          <small>{summary.retrying} retrying</small>
        </div>
        <div className="stat-card accent-teal">
          <span>Run time</span>
          <strong>{formatDuration(execution.started_at, execution.finished_at)}</strong>
          <small>{execution.finished_at ? "finished" : "in progress"}</small>
        </div>
        <div className="stat-card accent-green">
          <span>Logs</span>
          <strong>{logs.length}</strong>
          <small>{logs.filter((log) => log.level === "ERROR").length} errors</small>
        </div>
      </div>

      <div className="panel">
        <div className="panel-heading">
          <h3>Task graph</h3>
          <p className="muted">Select a task to inspect its configuration and actions.</p>
        </div>
        <TaskGraph tasks={tasks} selectedTask={selectedTask} onSelectTask={(task) => setSelectedTask(task.task_name)} />
      </div>

      <div className="detail-columns">
        <div className="panel">
          <div className="panel-heading">
            <h3>Tasks</h3>
          </div>
          <div className="table-wrap">
            <table className="data-table compact">
              <caption className="visually-hidden">Execution tasks</caption>
              <thead>
                <tr>
                  <th scope="col">Task</th>
                  <th scope="col">Status</th>
                  <th scope="col">Retries</th>
                  <th scope="col">Duration</th>
                  <th scope="col">Worker</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {tasks.map((task) => (
                  <tr
                    key={task.id}
                    className={selectedTask === task.task_name ? "selected-row" : ""}
                    onClick={() => setSelectedTask(task.task_name)}
                  >
                    <td>
                      <button className="link-button" onClick={() => setSelectedTask(task.task_name)}>
                        {task.task_name}
                      </button>
                      {task.error_message ? <span className="muted small block">{task.error_message}</span> : null}
                    </td>
                    <td>
                      <StatusPill status={task.status} />
                    </td>
                    <td>{task.retries}</td>
                    <td>{formatDuration(task.started_at, task.finished_at)}</td>
                    <td className="muted small">{task.worker_id || "—"}</td>
                    <td>
                      <div className="row-actions">
                        {canOperate && ["failed", "cancelled", "skipped", "pending"].includes(task.status) ? (
                          <button
                            className="small ghost-button"
                            onClick={(event) => {
                              event.stopPropagation();
                              doAction(`Retry ${task.task_name}`, api.retryTask(executionId, task.task_name));
                            }}
                            disabled={Boolean(action)}
                          >
                            Retry
                          </button>
                        ) : null}
                        {canOperate && ["failed", "pending", "cancelled"].includes(task.status) ? (
                          <button
                            className="small ghost-button"
                            onClick={(event) => {
                              event.stopPropagation();
                              doAction(`Skip ${task.task_name}`, api.skipTask(executionId, task.task_name));
                            }}
                            disabled={Boolean(action)}
                          >
                            Skip
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="panel">
          <div className="panel-heading">
            <h3>{currentTask ? currentTask.task_name : "Task details"}</h3>
            <p className="muted">
              {currentTask ? `Status: ${currentTask.status}` : "Choose a task from the graph or table."}
            </p>
          </div>
          {currentTask ? (
            <dl className="detail-list">
              <div>
                <dt>Started</dt>
                <dd>{formatDate(currentTask.started_at)}</dd>
              </div>
              <div>
                <dt>Finished</dt>
                <dd>{formatDate(currentTask.finished_at)}</dd>
              </div>
              <div>
                <dt>Dependencies</dt>
                <dd>{currentTask.dependencies.length ? currentTask.dependencies.join(", ") : "none"}</dd>
              </div>
              <div>
                <dt>Error</dt>
                <dd className={currentTask.error_message ? "error-text" : ""}>{currentTask.error_message || "—"}</dd>
              </div>
              <div className="span-2">
                <dt>Config</dt>
                <dd>
                  <pre className="code-block">{JSON.stringify(currentTask.config, null, 2)}</pre>
                </dd>
              </div>
            </dl>
          ) : (
            <div className="empty-state">No task selected.</div>
          )}
        </div>
      </div>

      <div className="panel">
        <div className="panel-heading log-heading">
          <div>
            <h3>Execution logs</h3>
            <p className="muted">Streamed over WebSocket; polling continues as a fallback.</p>
          </div>
          <div className="toolbar compact">
            <label className="inline-field">
              <span>Level</span>
              <select value={level} onChange={(event) => setLevel(event.target.value)}>
                {LEVELS.map((value) => (
                  <option key={value} value={value}>
                    {value || "All"}
                  </option>
                ))}
              </select>
            </label>
            <label className="checkbox-field">
              <input type="checkbox" checked={autoScroll} onChange={(event) => setAutoScroll(event.target.checked)} />
              Follow
            </label>
          </div>
        </div>
        <div className="log-list" role="log" aria-live="polite">
          {filteredLogs.map((log) => (
            <div key={log.id} className={`log-row level-${log.level.toLowerCase()}`}>
              <span className="log-time">{formatDate(log.created_at)}</span>
              <span className={`log-level ${log.level.toLowerCase()}`}>{log.level}</span>
              <span className="log-message">{log.message}</span>
            </div>
          ))}
          {!filteredLogs.length ? <div className="empty-state">No logs for this filter yet.</div> : null}
          <div ref={logEndRef} />
        </div>
      </div>

      <ConfirmDialog
        open={pendingCancel}
        title="Cancel this execution?"
        description="Pending and running tasks will be cancelled. Completed work is preserved."
        confirmLabel="Cancel execution"
        onCancel={() => setPendingCancel(false)}
        onConfirm={cancel}
      />
    </section>
  );
}
