const API_BASE = (import.meta.env.VITE_API_BASE_URL || "/api/v1").replace(/\/$/, "");
const API_ROOT = (import.meta.env.VITE_API_ROOT_URL || "").replace(/\/$/, "");
const WS_BASE =
  import.meta.env.VITE_WS_BASE_URL ||
  (typeof window !== "undefined" && window.location.protocol === "https:"
    ? `wss://${window.location.host}`
    : `ws://${window.location.host}`);
const REQUEST_TIMEOUT_MS = 20000;
const STORAGE_KEY = "devflow.apiKey";

let apiKey = typeof localStorage !== "undefined" ? localStorage.getItem(STORAGE_KEY) || "" : "";

export class ApiError extends Error {
  constructor(message, { status = 0, code = "error", details = null, requestId = null } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

export const auth = {
  getKey: () => apiKey,
  setKey: (value) => {
    apiKey = value.trim();
    localStorage.setItem(STORAGE_KEY, apiKey);
  },
  clearKey: () => {
    apiKey = "";
    localStorage.removeItem(STORAGE_KEY);
  },
  hasKey: () => Boolean(apiKey)
};

async function fetchJson(path, options = {}) {
  const { method = "GET", body, headers = {}, idempotencyKey, timeout = REQUEST_TIMEOUT_MS } = options;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(`${API_BASE}${path}`, {
      method,
      headers: {
        Accept: "application/json",
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(apiKey ? { "X-API-Key": apiKey } : {}),
        ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
        ...headers
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal
    });

    if (response.status === 204) {
      return null;
    }

    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      if (response.status === 401 && typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent("devflow:unauthorized"));
      }
      throw new ApiError(payload?.message || payload?.detail || `Request failed with status ${response.status}.`, {
        status: response.status,
        code: payload?.code || "error",
        details: payload?.details ?? null,
        requestId: payload?.request_id || response.headers.get("X-Request-ID")
      });
    }
    return payload;
  } catch (error) {
    if (error.name === "AbortError") {
      throw new ApiError("The request timed out. Check that the API is running.");
    }
    if (error instanceof TypeError) {
      throw new ApiError("Cannot reach the DevFlow API. Check the connection and API URL.");
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

async function fetchRoot(path) {
  const response = await fetch(`${API_ROOT}${path}`, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new ApiError(`Health check failed with status ${response.status}.`, { status: response.status });
  }
  return response.json();
}

const query = (params = {}) => {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  });
  const suffix = search.toString();
  return suffix ? `?${suffix}` : "";
};

export const api = {
  me: () => fetchJson("/auth/me"),
  listApiKeys: () => fetchJson("/auth/keys"),
  createApiKey: (payload) => fetchJson("/auth/keys", { method: "POST", body: payload }),
  revokeApiKey: (keyId) => fetchJson(`/auth/keys/${keyId}`, { method: "DELETE" }),

  listTemplates: () => fetchJson("/workflows/templates"),
  listWorkflows: (params) => fetchJson(`/workflows${query(params)}`),
  getWorkflow: (id) => fetchJson(`/workflows/${id}`),
  createWorkflow: (payload) => fetchJson("/workflows", { method: "POST", body: payload }),
  updateWorkflow: (id, payload) => fetchJson(`/workflows/${id}`, { method: "PATCH", body: payload }),
  deleteWorkflow: (id) => fetchJson(`/workflows/${id}`, { method: "DELETE" }),
  cloneWorkflow: (id, name) => fetchJson(`/workflows/${id}/clone`, { method: "POST", body: { name } }),
  listRevisions: (id) => fetchJson(`/workflows/${id}/revisions`),

  listExecutions: (params) => fetchJson(`/executions${query(params)}`),
  getExecution: (id) => fetchJson(`/executions/${id}`),
  getExecutionTasks: (id) => fetchJson(`/executions/${id}/tasks`),
  getExecutionLogs: (id, params) => fetchJson(`/executions/${id}/logs${query(params)}`),
  runWorkflow: (id, idempotencyKey) =>
    fetchJson(`/workflows/${id}/run`, { method: "POST", idempotencyKey }),
  cancelExecution: (id) => fetchJson(`/executions/${id}/cancel`, { method: "POST" }),
  retryExecution: (id) => fetchJson(`/executions/${id}/retry`, { method: "POST" }),
  retryTask: (executionId, taskIdentifier) =>
    fetchJson(`/executions/${executionId}/tasks/${encodeURIComponent(taskIdentifier)}/retry`, { method: "POST" }),
  skipTask: (executionId, taskIdentifier) =>
    fetchJson(`/executions/${executionId}/tasks/${encodeURIComponent(taskIdentifier)}/skip`, { method: "POST" }),

  listSchedules: (workflowId) => fetchJson(`/workflows/${workflowId}/schedules`),
  createSchedule: (workflowId, payload) => fetchJson(`/workflows/${workflowId}/schedules`, { method: "POST", body: payload }),
  deleteSchedule: (scheduleId) => fetchJson(`/schedules/${scheduleId}`, { method: "DELETE" }),

  queueStatus: () => fetchJson("/queue/status"),
  workerStatus: () => fetchJson("/workers/status"),
  systemSnapshot: () => fetchJson("/system/snapshot"),

  auditLog: (params) => fetchJson(`/audit${query(params)}`),
  listSecrets: () => fetchJson("/secrets"),
  createSecret: (payload) => fetchJson("/secrets", { method: "POST", body: payload }),
  deleteSecret: (name) => fetchJson(`/secrets/${encodeURIComponent(name)}`, { method: "DELETE" }),
  listWebhooks: () => fetchJson("/webhooks"),
  createWebhook: (payload) => fetchJson("/webhooks", { method: "POST", body: payload }),
  deleteWebhook: (id) => fetchJson(`/webhooks/${id}`, { method: "DELETE" }),
  listDeliveries: (params) => fetchJson(`/webhooks/deliveries${query(params)}`),
  listDeadLetters: (params) => fetchJson(`/queue/dead-letters${query(params)}`),
  replayDeadLetter: (jobId) => fetchJson(`/queue/dead-letters/${jobId}/replay`, { method: "POST" }),
  diagnostics: () => fetchJson("/diagnostics"),

  getHealth: () => fetchRoot("/health"),
  getReadiness: () => fetchRoot("/health/ready"),
  executionSocket: (executionId) =>
    new WebSocket(`${WS_BASE}/ws/executions/${executionId}?api_key=${encodeURIComponent(apiKey)}`)
};
