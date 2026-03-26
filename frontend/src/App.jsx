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
  const [execution, setExecution] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [logs, setLogs] = useState([]);
  const [queue, setQueue] = useState(null);
  const [workers, setWorkers] = useState([]);
  const [error, setError] = useState("");

  const selectedExecutionId = execution?.id || "";

  const loadWorkflows = async () => {
    const data = await api.listWorkflows();
    setWorkflows(data);
  };

  const loadRuntime = async () => {
    const [queueData, workersData] = await Promise.all([api.getQueueStatus(), api.getWorkersStatus()]);
    setQueue(queueData);
    setWorkers(workersData);
  };

  const loadExecution = async (executionId) => {
    if (!executionId) {
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
  };

  const handleRunWorkflow = async (workflowId) => {
    const run = await api.runWorkflow(workflowId);
    await loadExecution(run.id);
    await loadRuntime();
    setActivePage("executions");
  };

  return (
    <div className="app-shell">
      <Header activePage={activePage} setActivePage={setActivePage} />

      {error ? <div className="global-error">{error}</div> : null}

      {activePage === "builder" ? (
        <WorkflowBuilderPage
          workflows={workflows}
          onCreateWorkflow={handleCreateWorkflow}
          onRunWorkflow={handleRunWorkflow}
          lastExecutionId={selectedExecutionId}
        />
      ) : null}

      {activePage === "executions" ? (
        <ExecutionDashboardPage execution={execution} tasks={tasks} workflows={workflows} />
      ) : null}

      {activePage === "logs" ? <LogsViewPage logs={logs} /> : null}

      {activePage === "workers" ? <WorkerMonitorPage queue={queue} workers={workers} /> : null}
    </div>
  );
}
