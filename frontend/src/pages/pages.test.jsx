import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ExecutionDetailPage from "../pages/ExecutionDetailPage.jsx";
import ExecutionsPage from "../pages/ExecutionsPage.jsx";
import LoginPage from "../pages/LoginPage.jsx";
import MonitorPage from "../pages/MonitorPage.jsx";
import WorkflowsPage from "../pages/WorkflowsPage.jsx";

const { api, auth } = vi.hoisted(() => ({
  api: {
    me: vi.fn(),
    listWorkflows: vi.fn(),
    listTemplates: vi.fn(),
    runWorkflow: vi.fn(),
    cloneWorkflow: vi.fn(),
    deleteWorkflow: vi.fn(),
    createWorkflow: vi.fn(),
    queueStatus: vi.fn(),
    getHealth: vi.fn(),
    getReadiness: vi.fn(),
    workerStatus: vi.fn(),
    listExecutions: vi.fn(),
    cancelExecution: vi.fn(),
    retryExecution: vi.fn(),
    getExecution: vi.fn(),
    getExecutionTasks: vi.fn(),
    getExecutionLogs: vi.fn(),
    executionSocket: vi.fn(),
    retryTask: vi.fn(),
    skipTask: vi.fn()
  },
  auth: {
    getKey: vi.fn(() => ""),
    setKey: vi.fn(),
    clearKey: vi.fn()
  }
}));

vi.mock("../services/api", () => ({ api, auth }));

const workflow = {
  id: "wf-123456789",
  name: "ML pipeline",
  description: "Train and evaluate",
  current_revision: 2,
  is_archived: false,
  updated_at: "2026-10-29T10:00:00",
  tasks: [{ id: "t1", name: "train" }, { id: "t2", name: "evaluate" }]
};

beforeEach(() => {
  vi.clearAllMocks();
  window.location.hash = "";
  vi.stubGlobal("crypto", { randomUUID: () => "idem-test" });
  Element.prototype.scrollIntoView = vi.fn();
  api.listWorkflows.mockResolvedValue({ items: [workflow], total: 1 });
  api.listTemplates.mockResolvedValue([
    { name: "ETL starter", description: "Extract and load", tasks: [{ name: "extract" }] }
  ]);
});

describe("LoginPage", () => {
  it("verifies a key and reports the principal", async () => {
    auth.getKey.mockReturnValue("dvf_key");
    api.me.mockResolvedValue({ role: "admin", key_name: "bootstrap" });
    const onAuthenticated = vi.fn();

    render(<LoginPage onAuthenticated={onAuthenticated} />);
    expect(screen.getByLabelText("API key")).toHaveValue("dvf_key");

    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    await waitFor(() => expect(onAuthenticated).toHaveBeenCalledWith({ role: "admin", key_name: "bootstrap" }));
    expect(auth.setKey).toHaveBeenCalledWith("dvf_key");
  });

  it("shows a clear message when the key is rejected", async () => {
    auth.getKey.mockReturnValue("bad-key");
    api.me.mockRejectedValue(Object.assign(new Error("Invalid API key."), { status: 401 }));

    render(<LoginPage onAuthenticated={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("That API key was rejected.");
    expect(auth.clearKey).toHaveBeenCalled();
  });
});

describe("WorkflowsPage", () => {
  it("lists workflows, filters, and runs an execution", async () => {
    api.runWorkflow.mockResolvedValue({ id: "exec-1" });
    const notify = vi.fn();

    render(<WorkflowsPage me={{ role: "admin" }} notify={notify} />);

    expect(await screen.findByText("ML pipeline")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("r2")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("Filter by name or description"), {
      target: { value: "nothing" }
    });
    expect(screen.getByText("No workflows match your search")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("Filter by name or description"), {
      target: { value: "train" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Run" }));
    expect(screen.getByRole("dialog", { name: "Start a new run?" })).toBeInTheDocument();
    expect(api.runWorkflow).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Start run" }));

    await waitFor(() => expect(api.runWorkflow).toHaveBeenCalledWith("wf-123456789", "idem-test"));
    expect(notify).toHaveBeenCalledWith("Started “ML pipeline”.", "success");
    expect(window.location.hash).toBe("#/executions/exec-1");
  });

  it("clones, archives with confirmation, and creates from a template", async () => {
    api.cloneWorkflow.mockResolvedValue({ ...workflow, id: "wf-copy", name: "ML pipeline (copy)" });
    api.deleteWorkflow.mockResolvedValue(null);
    api.createWorkflow.mockResolvedValue({ id: "wf-template" });
    const notify = vi.fn();

    render(<WorkflowsPage me={{ role: "admin" }} notify={notify} />);
    await screen.findByText("ML pipeline");

    fireEvent.click(screen.getByRole("button", { name: "Clone" }));
    expect(await screen.findByText("ML pipeline (copy)")).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: "Archive" })[0]);
    expect(screen.getByRole("dialog", { name: "Archive workflow?" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Archive workflow" }));
    await waitFor(() => expect(api.deleteWorkflow).toHaveBeenCalledWith("wf-copy"));
    expect(notify).toHaveBeenCalledWith("Workflow archived.", "success");

    fireEvent.click(screen.getByRole("button", { name: "Use template" }));
    await waitFor(() => expect(api.createWorkflow).toHaveBeenCalled());
    expect(api.createWorkflow.mock.calls[0][0]).toMatchObject({ name: "ETL starter" });
  });

  it("surfaces load failures", async () => {
    api.listWorkflows.mockRejectedValue(new Error("API is down"));

    render(<WorkflowsPage me={{ role: "viewer" }} notify={vi.fn()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("API is down");
    expect(screen.queryByRole("link", { name: "New workflow" })).not.toBeInTheDocument();
  });
});

describe("ExecutionsPage", () => {
  it("requires confirmation before cancelling a running execution", async () => {
    api.listExecutions.mockResolvedValue({
      items: [
        {
          id: "exec-123456789",
          workflow_id: "wf-123456789",
          workflow_name: "ML pipeline",
          revision: 2,
          status: "running",
          triggered_by: "bootstrap",
          created_at: "2026-10-29T10:00:00",
          started_at: "2026-10-29T10:00:00",
          finished_at: null
        }
      ],
      total: 1
    });
    api.cancelExecution.mockResolvedValue({ status: "cancelled" });
    const notify = vi.fn();

    render(<ExecutionsPage routeQuery={new URLSearchParams()} notify={notify} />);

    expect(await screen.findByRole("table")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("dialog", { name: "Cancel execution?" })).toBeInTheDocument();
    expect(api.cancelExecution).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Cancel execution" }));
    await waitFor(() => expect(api.cancelExecution).toHaveBeenCalledWith("exec-123456789"));
    expect(notify).toHaveBeenCalledWith("Cancellation requested.", "success");
  });
});

describe("MonitorPage", () => {
  it("renders queue and worker state for admins", async () => {
    api.queueStatus.mockResolvedValue({
      queued_jobs: 12,
      delayed_jobs: 1,
      in_flight_jobs: 3,
      total_processed: 44,
      total_enqueued: 60,
      dead_letter_jobs: 0,
      queue_backend: "database"
    });
    api.getHealth.mockResolvedValue({ status: "ok", version: "2.0.0", environment: "test" });
    api.getReadiness.mockResolvedValue({ status: "ok", database: "ok", workers: "running" });
    api.workerStatus.mockResolvedValue([
      { worker_id: "w-1", state: "running", processed_jobs: 10, failed_jobs: 0 }
    ]);

    render(<MonitorPage me={{ role: "admin" }} />);

    expect(await screen.findByText("12")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("44")).toBeInTheDocument();
    expect(await screen.findByText("w-1")).toBeInTheDocument();
    expect(api.workerStatus).toHaveBeenCalled();
  });

  it("hides worker registration from non-admins", async () => {
    api.queueStatus.mockResolvedValue({ queued_jobs: 0, delayed_jobs: 0, in_flight_jobs: 0, total_processed: 0 });
    api.getHealth.mockResolvedValue({ status: "ok" });
    api.getReadiness.mockRejectedValue(new Error("readiness unavailable"));

    render(<MonitorPage me={{ role: "viewer" }} />);

    expect(await screen.findByText("admin key required")).toBeInTheDocument();
    expect(api.workerStatus).not.toHaveBeenCalled();
  });
});

describe("ExecutionDetailPage", () => {
  it("reconnects the live socket after it drops", async () => {
    const sockets = [];
    api.executionSocket.mockImplementation(() => {
      const socket = {
        onopen: null,
        onmessage: null,
        onclose: null,
        onerror: null,
        send: vi.fn(),
        close: vi.fn()
      };
      sockets.push(socket);
      return socket;
    });
    api.getExecution.mockResolvedValue({
      id: "exec-1",
      workflow_name: "Realtime pipeline",
      status: "running",
      revision: 1,
      created_at: "2026-10-29T10:00:00",
      started_at: "2026-10-29T10:00:01",
      finished_at: null
    });
    api.getExecutionTasks.mockResolvedValue([
      { id: "task-1", task_name: "prepare", status: "running", dependencies: [] }
    ]);
    api.getExecutionLogs.mockResolvedValue({ items: [] });

    render(<ExecutionDetailPage executionId="exec-1" me={{ role: "admin" }} notify={vi.fn()} />);

    await waitFor(() => expect(sockets.length).toBe(1));
    await waitFor(() => expect(api.getExecution).toHaveBeenCalledWith("exec-1"));

    vi.useFakeTimers();
    try {
      act(() => sockets[0].onclose());
      act(() => vi.advanceTimersByTime(5000));
      expect(sockets.length).toBe(2);
    } finally {
      vi.useRealTimers();
    }
  });
});
