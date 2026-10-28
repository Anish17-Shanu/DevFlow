const API_BASE = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api").replace(/\/$/, "");
const API_ROOT = API_BASE.replace(/\/api$/, "");
const WS_BASE = (import.meta.env.VITE_WS_BASE_URL || "ws://localhost:8000").replace(/\/$/, "");
const REQUEST_TIMEOUT_MS = 15000;

async function fetchJson(url, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch(url, {
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {})
      },
      ...options,
      signal: controller.signal
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => ({ detail: "Request failed" }));
      throw new Error(payload.detail || `Request failed with status ${response.status}.`);
    }

    if (response.status === 204) {
      return null;
    }

    return response.json().catch(() => null);
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("Request timed out.");
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

const request = (path, options) => fetchJson(`${API_BASE}${path}`, options);
const requestRoot = (path) => fetchJson(`${API_ROOT}${path}`);

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
  getHealth: () => requestRoot("/health"),
  getReadiness: () => requestRoot("/health/ready"),
  executionSocket: (executionId) => new WebSocket(`${WS_BASE}/ws/executions/${executionId}`)
};
