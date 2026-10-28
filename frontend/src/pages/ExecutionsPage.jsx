import { useCallback, useEffect, useMemo, useState } from "react";

import ConfirmDialog from "../components/ConfirmDialog";
import EmptyState from "../components/EmptyState";
import StatusPill from "../components/StatusPill";
import { formatDuration, formatRelative, shortId } from "../lib/format";
import { pathFor } from "../lib/router";
import { api } from "../services/api";

const PAGE_SIZE = 25;
const STATUSES = ["", "running", "pending", "success", "failed", "cancelled"];

export default function ExecutionsPage({ routeQuery, notify }) {
  const initialWorkflow = routeQuery.get("workflow") || "";
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [status, setStatus] = useState("");
  const [workflowId, setWorkflowId] = useState(initialWorkflow);
  const [workflows, setWorkflows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionId, setActionId] = useState("");
  const [pendingCancel, setPendingCancel] = useState(null);

  const load = useCallback(
    async ({ silent = false } = {}) => {
      if (!silent) setLoading(true);
      setError("");
      try {
        const result = await api.listExecutions({
          limit: PAGE_SIZE,
          offset,
          status: status || undefined,
          workflow_id: workflowId || undefined
        });
        setItems(result.items || []);
        setTotal(result.total || 0);
      } catch (loadError) {
        setError(loadError.message);
      } finally {
        setLoading(false);
      }
    },
    [offset, status, workflowId]
  );

  useEffect(() => {
    api.listWorkflows({ limit: 200 }).then((result) => setWorkflows(result.items || [])).catch(() => undefined);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const interval = setInterval(() => {
      if (document.visibilityState === "visible") load({ silent: true });
    }, 5000);
    return () => clearInterval(interval);
  }, [load]);

  const workflowNames = useMemo(
    () => Object.fromEntries(workflows.map((workflow) => [workflow.id, workflow.name])),
    [workflows]
  );

  const cancel = async (execution) => {
    setActionId(execution.id);
    try {
      await api.cancelExecution(execution.id);
      notify("Cancellation requested.", "success");
      await load({ silent: true });
    } catch (cancelError) {
      notify(cancelError.message, "error");
    } finally {
      setActionId("");
    }
  };

  const retry = async (execution) => {
    setActionId(execution.id);
    try {
      const copy = await api.retryExecution(execution.id);
      notify("Execution retried.", "success");
      window.location.hash = `#/${pathFor.execution(copy.id)}`;
    } catch (retryError) {
      notify(retryError.message, "error");
    } finally {
      setActionId("");
    }
  };

  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <section className="page-stack">
      <div className="page-heading">
        <div>
          <p className="eyebrow">History</p>
          <h2>Executions</h2>
          <p className="muted">Every run is snapshotted against an immutable workflow revision.</p>
        </div>
        <a className="button-link" href="#/workflows">
          Run a workflow
        </a>
      </div>

      <div className="toolbar">
        <label className="inline-field">
          <span>Status</span>
          <select value={status} onChange={(event) => { setStatus(event.target.value); setOffset(0); }}>
            {STATUSES.map((value) => (
              <option key={value} value={value}>
                {value ? value : "All statuses"}
              </option>
            ))}
          </select>
        </label>
        <label className="inline-field">
          <span>Workflow</span>
          <select value={workflowId} onChange={(event) => { setWorkflowId(event.target.value); setOffset(0); }}>
            <option value="">All workflows</option>
            {workflows.map((workflow) => (
              <option key={workflow.id} value={workflow.id}>
                {workflow.name}
              </option>
            ))}
          </select>
        </label>
        <button className="secondary-button" onClick={() => load()} disabled={loading}>
          {loading ? "Loading…" : "Reload"}
        </button>
      </div>

      {error ? (
        <div className="error-text" role="alert">
          {error}
        </div>
      ) : null}

      {!loading && !items.length ? (
        <EmptyState title="No executions found" description="Adjust the filters or run a workflow to create history." />
      ) : null}

      {items.length ? (
        <div className="table-wrap">
          <table className="data-table">
            <caption className="visually-hidden">Execution history</caption>
            <thead>
              <tr>
                <th scope="col">Execution</th>
                <th scope="col">Workflow</th>
                <th scope="col">Status</th>
                <th scope="col">Triggered by</th>
                <th scope="col">Duration</th>
                <th scope="col">Started</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((execution) => (
                <tr key={execution.id}>
                  <td>
                    <a href={`#/${pathFor.execution(execution.id)}`} className="mono-link">
                      {shortId(execution.id)}
                    </a>
                    <span className="muted small">r{execution.revision}</span>
                  </td>
                  <td>{execution.workflow_name || workflowNames[execution.workflow_id] || shortId(execution.workflow_id)}</td>
                  <td>
                    <StatusPill status={execution.status} />
                  </td>
                  <td className="muted">{execution.triggered_by}</td>
                  <td>{formatDuration(execution.started_at, execution.finished_at)}</td>
                  <td className="muted">{formatRelative(execution.created_at)}</td>
                  <td>
                    <div className="row-actions">
                      {execution.status === "running" || execution.status === "pending" ? (
                        <button
                          className="small ghost-button"
                          onClick={() => setPendingCancel(execution)}
                          disabled={actionId === execution.id}
                        >
                          Cancel
                        </button>
                      ) : null}
                      {["success", "failed", "cancelled"].includes(execution.status) ? (
                        <button className="small ghost-button" onClick={() => retry(execution)} disabled={actionId === execution.id}>
                          Retry
                        </button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      <div className="pagination">
        <button className="secondary-button" onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))} disabled={offset === 0 || loading}>
          Previous
        </button>
        <span className="muted">
          Page {page} of {pages} · {total} executions
        </span>
        <button
          className="secondary-button"
          onClick={() => setOffset(offset + PAGE_SIZE)}
          disabled={offset + PAGE_SIZE >= total || loading}
        >
          Next
        </button>
      </div>

      <ConfirmDialog
        open={Boolean(pendingCancel)}
        title="Cancel execution?"
        description={
          pendingCancel
            ? `Execution ${shortId(pendingCancel.id)} will be cancelled. Running tasks are stopped and queued tasks are skipped. This can’t be undone.`
            : ""
        }
        confirmLabel="Cancel execution"
        onCancel={() => setPendingCancel(null)}
        onConfirm={() => {
          const target = pendingCancel;
          setPendingCancel(null);
          if (target) cancel(target);
        }}
      />
    </section>
  );
}
