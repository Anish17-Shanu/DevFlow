import { useCallback, useEffect, useState } from "react";

import EmptyState from "../components/EmptyState";
import StatusPill from "../components/StatusPill";
import { formatDate, formatRelative } from "../lib/format";
import { api } from "../services/api";

export default function MonitorPage({ me }) {
  const [queue, setQueue] = useState(null);
  const [workers, setWorkers] = useState([]);
  const [health, setHealth] = useState(null);
  const [readiness, setReadiness] = useState(null);
  const [error, setError] = useState("");
  const [updatedAt, setUpdatedAt] = useState(null);

  const isAdmin = me?.role === "admin";

  const load = useCallback(async () => {
    const results = await Promise.allSettled([api.queueStatus(), api.getHealth(), api.getReadiness(), isAdmin ? api.workerStatus() : api.queueStatus()]);
    const [queueResult, healthResult, readinessResult, workerResult] = results;
    if (queueResult.status === "fulfilled") setQueue(queueResult.value);
    if (healthResult.status === "fulfilled") setHealth(healthResult.value);
    if (readinessResult.status === "fulfilled") setReadiness(readinessResult.value);
    if (workerResult.status === "fulfilled" && isAdmin) setWorkers(workerResult.value || []);
    const failure = queueResult.status === "rejected" ? queueResult.reason : null;
    setError(failure ? failure.message : "");
    setUpdatedAt(new Date());
  }, [isAdmin]);

  useEffect(() => {
    load();
    const interval = setInterval(() => {
      if (document.visibilityState === "visible") load();
    }, 5000);
    return () => clearInterval(interval);
  }, [load]);

  const platformStatus = readiness?.status || health?.status || "unknown";

  return (
    <section className="page-stack">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Runtime</p>
          <h2>Monitor</h2>
          <p className="muted">
            Health, queue depth, and worker heartbeats. Updated {updatedAt ? formatRelative(updatedAt.toISOString()) : "…"}.
          </p>
        </div>
        <StatusPill status={platformStatus === "ok" ? "success" : platformStatus === "degraded" ? "retrying" : "pending"} label={platformStatus} />
      </div>

      {error ? (
        <div className="error-text" role="alert">
          {error}
        </div>
      ) : null}

      <div className="stats-grid">
        <div className="stat-card accent-blue">
          <span>Queued</span>
          <strong>{queue?.queued_jobs ?? "—"}</strong>
          <small>{queue?.delayed_jobs ?? 0} delayed</small>
        </div>
        <div className="stat-card accent-amber">
          <span>In flight</span>
          <strong>{queue?.in_flight_jobs ?? "—"}</strong>
          <small>{queue?.dead_letter_jobs ?? 0} dead letters</small>
        </div>
        <div className="stat-card accent-teal">
          <span>Processed</span>
          <strong>{queue?.total_processed ?? "—"}</strong>
          <small>{queue?.total_enqueued ?? 0} enqueued</small>
        </div>
        <div className="stat-card accent-green">
          <span>Workers</span>
          <strong>{isAdmin ? workers.filter((worker) => worker.state !== "offline").length : "—"}</strong>
          <small>{isAdmin ? `${workers.length} registered` : "admin key required"}</small>
        </div>
      </div>

      <div className="detail-columns">
        <div className="panel">
          <div className="panel-heading">
            <h3>Queue</h3>
            <p className="muted">{queue?.queue_backend || "unknown"} backend</p>
          </div>
          {queue ? (
            <dl className="detail-list">
              <div>
                <dt>Healthy</dt>
                <dd>
                  <StatusPill status={queue.healthy ? "success" : "failed"} label={queue.healthy ? "Healthy" : "Unhealthy"} />
                </dd>
              </div>
              <div>
                <dt>Durable</dt>
                <dd>{queue.is_durable ? "Yes" : "No"}</dd>
              </div>
              <div>
                <dt>Dead letters</dt>
                <dd>{queue.dead_letter_jobs ?? 0}</dd>
              </div>
              <div>
                <dt>Last error</dt>
                <dd>{queue.error || "—"}</dd>
              </div>
            </dl>
          ) : (
            <EmptyState title="Queue unavailable" />
          )}
        </div>

        <div className="panel">
          <div className="panel-heading">
            <h3>Service health</h3>
          </div>
          <dl className="detail-list">
            <div>
              <dt>Database</dt>
              <dd>{readiness?.database || "—"}</dd>
            </div>
            <div>
              <dt>Workers</dt>
              <dd>{readiness?.workers || "—"}</dd>
            </div>
            <div>
              <dt>Version</dt>
              <dd>{health?.version || "—"}</dd>
            </div>
            <div>
              <dt>Environment</dt>
              <dd>{health?.environment || "—"}</dd>
            </div>
          </dl>
        </div>
      </div>

      <div className="panel">
        <div className="panel-heading">
          <h3>Workers</h3>
          <p className="muted">{isAdmin ? "Heartbeats from every worker process." : "Worker details require an admin key."}</p>
        </div>
        {isAdmin && workers.length ? (
          <div className="table-wrap">
            <table className="data-table">
              <caption className="visually-hidden">Worker status</caption>
              <thead>
                <tr>
                  <th scope="col">Worker</th>
                  <th scope="col">State</th>
                  <th scope="col">Current execution</th>
                  <th scope="col">Processed</th>
                  <th scope="col">Failed</th>
                  <th scope="col">Last seen</th>
                  <th scope="col">Last error</th>
                </tr>
              </thead>
              <tbody>
                {workers.map((worker) => (
                  <tr key={worker.worker_id}>
                    <td className="mono-small">{worker.worker_id}</td>
                    <td>
                      <StatusPill status={worker.state} />
                    </td>
                    <td className="mono-small">{worker.current_execution_id || "—"}</td>
                    <td>{worker.processed_jobs}</td>
                    <td>{worker.failed_jobs}</td>
                    <td className="muted" title={formatDate(worker.last_seen_at)}>
                      {formatRelative(worker.last_seen_at)}
                    </td>
                    <td className="muted small">{worker.last_error || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title={isAdmin ? "No active workers" : "Admin access required"}
            description={isAdmin ? "Start the worker process to see heartbeats." : undefined}
          />
        )}
      </div>
    </section>
  );
}
