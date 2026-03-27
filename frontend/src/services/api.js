const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";
const WS_BASE = (import.meta.env.VITE_WS_BASE_URL || "ws://localhost:8000").replace(/\/$/, "");

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    },
    ...options
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(payload.detail || "Request failed");
  }

  if (response.status === 204) {
    return null;
  }

  return response.json().catch(() => null);
}

export const api = {
  listWorkflows: () => request("/workflows"),
  createWorkflow: (payload) =>
    request("/workflows", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  runWorkflow: (id) =>
    request(`/workflows/${id}/run`, {
      method: "POST"
    }),
  getExecution: (id) => request(`/executions/${id}`),
  getExecutionTasks: (id) => request(`/executions/${id}/tasks`),
  getExecutionLogs: (id) => request(`/executions/${id}/logs`),
  getQueueStatus: () => request("/queue/status"),
  getWorkersStatus: () => request("/workers/status"),
  getSystemSnapshot: () => request("/system/snapshot"),
  getHealth: () => request("/health"),
  getReadiness: () => request("/health/ready"),
  executionSocket: (executionId) => new WebSocket(`${WS_BASE}/ws/executions/${executionId}`)
};
