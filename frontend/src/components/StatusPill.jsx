const LABELS = {
  success: "Succeeded",
  failed: "Failed",
  cancelled: "Cancelled",
  running: "Running",
  queued: "Queued",
  pending: "Pending",
  retrying: "Retrying",
  skipped: "Skipped",
  idle: "Idle",
  offline: "Offline",
  error: "Error",
  stopped: "Stopped",
  ok: "Operational",
  degraded: "Degraded"
};

export default function StatusPill({ status = "pending", label }) {
  return (
    <span className={`status-pill ${status}`} title={LABELS[status] || status}>
      <span className="status-dot" aria-hidden="true" />
      {label || LABELS[status] || status}
    </span>
  );
}
