import { useEffect, useState } from "react";

import Header from "./components/Header";
import ExecutionDashboardPage from "./pages/ExecutionDashboardPage";
import LogsViewPage from "./pages/LogsViewPage";
import WorkerMonitorPage from "./pages/WorkerMonitorPage";
import WorkflowBuilderPage from "./pages/WorkflowBuilderPage";
import { api } from "./services/api";

export default function App() {
  const [activePage, setActivePage] = useState("builder");
  const [workflows, setWorkflows] = useState([]);
  const [selectedWorkflowId, setSelectedWorkflowId] = useState("");
  const [execution, setExecution] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [logs, setLogs] = useState([]);
  const [queue, setQueue] = useState(null);
  const [workers, setWorkers] = useState([]);
  const [health, setHealth] = useState(null);
  const [readiness, setReadiness] = useState(null);
  const [isBooting, setIsBooting] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState("");

  const selectedExecutionId = execution?.id || "";

  const loadWorkflows = async () => {
    const data = await api.listWorkflows();
    setWorkflows(data);
    setSelectedWorkflowId((current) => current || data[0]?.id || "");
  };

  const loadRuntime = async () => {
    const [snapshotData, healthData, readinessData] = await Promise.all([
      api.getSystemSnapshot(),
      api.getHealth(),
      api.getReadiness()
    ]);
    setQueue(snapshotData?.queue ?? null);
    setWorkers(snapshotData?.workers ?? []);
    setHealth(healthData);
    setReadiness(readinessData);
  };

  const loadExecution = async (executionId) => {
    if (!executionId) {
      setExecution(null);
      setTasks([]);
      setLogs([]);
      return;
    }

    const [executionData, taskData, logData] = await Promise.all([
      api.getExecution(executionId),
      api.getExecutionTasks(executionId),
      api.getExecutionLogs(executionId)
    ]);

    setExecution(executionData);
    setTasks(taskData);
    setLogs(logData);
  };

  useEffect(() => {
    const boot = async () => {
      try {
        await Promise.all([loadWorkflows(), loadRuntime()]);
      } catch (bootError) {
        setError(bootError.message);
      } finally {
        setIsBooting(false);
      }
    };

    boot();
  }, []);

  useEffect(() => {
    const interval = setInterval(() => {
      loadRuntime().catch(() => undefined);
      if (selectedExecutionId) {
        loadExecution(selectedExecutionId).catch(() => undefined);
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [selectedExecutionId]);

  useEffect(() => {
    if (!selectedExecutionId) {
      return undefined;
    }

    const socket = api.executionSocket(selectedExecutionId);
    socket.onopen = () => socket.send("subscribe");
    socket.onmessage = () => loadExecution(selectedExecutionId).catch(() => undefined);
    socket.onerror = () => setError("Realtime stream disconnected. Falling back to polling.");

    return () => {
      socket.close();
    };
  }, [selectedExecutionId]);

  const handleCreateWorkflow = async (payload) => {
    const created = await api.createWorkflow(payload);
    setWorkflows((current) => [created, ...current]);
    setSelectedWorkflowId(created.id);
  };

  const handleRunWorkflow = async (workflowId) => {
    const run = await api.runWorkflow(workflowId);
    setSelectedWorkflowId(workflowId);
    await loadExecution(run.id);
    await loadRuntime();
    setActivePage("executions");
  };

  const handleRefresh = async () => {
    setIsRefreshing(true);
    setError("");
    try {
      await Promise.all([loadWorkflows(), loadRuntime(), loadExecution(selectedExecutionId)]);
    } catch (refreshError) {
      setError(refreshError.message);
    } finally {
      setIsRefreshing(false);
    }
  };

  return (
    <div className="app-shell">
      <Header
        activePage={activePage}
        setActivePage={setActivePage}
        health={health}
        readiness={readiness}
        onRefresh={handleRefresh}
        isRefreshing={isRefreshing}
      />

      {error ? <div className="global-error">{error}</div> : null}
      {isBooting ? <div className="empty-state">Loading control plane...</div> : null}

      {activePage === "builder" ? (
        <WorkflowBuilderPage
          workflows={workflows}
          onCreateWorkflow={handleCreateWorkflow}
          onRunWorkflow={handleRunWorkflow}
          lastExecutionId={selectedExecutionId}
          selectedWorkflowId={selectedWorkflowId}
        />
      ) : null}

      {activePage === "executions" ? (
        <ExecutionDashboardPage execution={execution} tasks={tasks} workflows={workflows} queue={queue} workers={workers} />
      ) : null}

      {activePage === "logs" ? <LogsViewPage logs={logs} execution={execution} /> : null}

      {activePage === "workers" ? <WorkerMonitorPage queue={queue} workers={workers} readiness={readiness} /> : null}
    </div>
  );
}
