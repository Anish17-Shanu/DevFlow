export function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value.endsWith?.("Z") ? value : `${value}Z`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

export function formatRelative(value) {
  if (!value) return "—";
  const date = new Date(value.endsWith?.("Z") ? value : `${value}Z`);
  const seconds = Math.round((Date.now() - date.getTime()) / 1000);
  if (Number.isNaN(seconds)) return value;
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

export function formatDuration(startedAt, finishedAt) {
  if (!startedAt) return "—";
  const start = new Date(startedAt.endsWith?.("Z") ? startedAt : `${startedAt}Z`);
  const end = finishedAt ? new Date(finishedAt.endsWith?.("Z") ? finishedAt : `${finishedAt}Z`) : new Date();
  const seconds = Math.max(0, (end.getTime() - start.getTime()) / 1000);
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

export function shortId(value) {
  return value ? value.slice(0, 8) : "—";
}
