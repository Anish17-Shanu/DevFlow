import { useCallback, useEffect, useMemo, useState } from "react";

import ConfirmDialog from "../components/ConfirmDialog";
import TaskGraph from "../components/TaskGraph";
import { formatDate } from "../lib/format";
import { navigate, pathFor } from "../lib/router";
import { api } from "../services/api";

let taskSequence = 0;

const TASK_TYPES = [
  { value: "sleep", label: "Sleep (delay)" },
  { value: "echo", label: "Echo (message)" },
  { value: "http", label: "HTTP request" }
];

const createTask = (overrides = {}) => ({
  key: `task-${Date.now()}-${taskSequence++}`,
  name: "",
  dependencies: "",
  type: "sleep",
  duration_ms: 800,
  max_retries: 0,
  fail_first_n: 0,
  backoff_seconds: 1,
  delay_seconds: 0,
  priority: 0,
  timeout_seconds: 60,
  allow_failure: false,
  method: "GET",
  url: "",
  expected_status: "",
  body: "",
  message: "",
  headersText: "",
  ...overrides
});

function workflowToTasks(workflow) {
  return workflow.tasks.map((task) => {
    const config = task.config || {};
    return createTask({
      name: task.name,
      dependencies: (task.dependencies || []).join(", "),
      type: config.type || "sleep",
      duration_ms: config.duration_ms ?? 800,
      max_retries: config.max_retries ?? 0,
      fail_first_n: config.fail_first_n ?? 0,
      backoff_seconds: config.backoff_seconds ?? 1,
      delay_seconds: config.delay_seconds ?? 0,
      priority: config.priority ?? 0,
      timeout_seconds: config.timeout_seconds ?? 60,
      allow_failure: Boolean(config.allow_failure),
      method: config.method || "GET",
      url: config.url || "",
      expected_status: config.expected_status ?? "",
      body: config.body || "",
      message: config.message || "",
      headersText: config.headers && Object.keys(config.headers).length ? JSON.stringify(config.headers, null, 2) : ""
    });
  });
}

const dependencyList = (task) =>
  task.dependencies
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

function validateTasks(tasks) {
  const errors = [];
  if (!tasks.length) errors.push("Add at least one task.");
  const names = tasks.map((task) => task.name.trim());
  if (names.some((name) => !name)) errors.push("Every task needs a name.");
  const duplicates = names.filter((name, index) => name && names.indexOf(name) !== index);
  if (duplicates.length) errors.push(`Duplicate task names: ${[...new Set(duplicates)].join(", ")}.`);

  const known = new Set(names.filter(Boolean));
  tasks.forEach((task) => {
    const label = task.name.trim() || "unnamed task";
    dependencyList(task).forEach((dependency) => {
      if (!known.has(dependency)) errors.push(`“${label}” depends on unknown task “${dependency}”.`);
      if (dependency === label) errors.push(`“${label}” cannot depend on itself.`);
    });
    if (Number(task.fail_first_n) > Number(task.max_retries) + 1) {
      errors.push(`“${label}”: fail-first count must be at most max retries + 1.`);
    }
    if (task.type === "http") {
      if (!task.url.trim()) errors.push(`“${label}”: HTTP tasks require a URL.`);
      else if (!/^https?:\/\//.test(task.url.trim())) errors.push(`“${label}”: URL must start with http:// or https://.`);
      if (task.headersText.trim()) {
        try {
          JSON.parse(task.headersText);
        } catch {
          errors.push(`“${label}”: headers must be valid JSON.`);
        }
      }
    }
  });

  const graph = new Map();
  tasks.forEach((task) => {
    const name = task.name.trim();
    if (!name) return;
    graph.set(name, dependencyList(task).filter((dependency) => known.has(dependency)));
  });
  const visiting = new Set();
  const visited = new Set();
  const hasCycle = (name) => {
    if (visiting.has(name)) return true;
    if (visited.has(name)) return false;
    visiting.add(name);
    for (const dependency of graph.get(name) || []) {
      if (hasCycle(dependency)) return true;
    }
    visiting.delete(name);
    visited.add(name);
    return false;
  };
  for (const name of graph.keys()) {
    if (hasCycle(name)) {
      errors.push("Dependencies contain a cycle. Workflows must be acyclic.");
      break;
    }
  }
  return [...new Set(errors)];
}

function taskPayload(task) {
  const config = {
    type: task.type,
    duration_ms: Number(task.duration_ms),
    max_retries: Number(task.max_retries),
    fail_first_n: Number(task.fail_first_n),
    backoff_seconds: Number(task.backoff_seconds),
    delay_seconds: Number(task.delay_seconds),
    priority: Number(task.priority),
    timeout_seconds: Number(task.timeout_seconds),
    allow_failure: Boolean(task.allow_failure)
  };
  if (task.type === "http") {
    config.method = task.method;
    config.url = task.url.trim();
    config.body = task.body ? task.body : null;
    if (task.expected_status !== "") config.expected_status = Number(task.expected_status);
    if (task.headersText.trim()) config.headers = JSON.parse(task.headersText);
  }
  if (task.type === "echo" && task.message) config.message = task.message;
  return { name: task.name.trim(), dependencies: dependencyList(task), config };
}

function previewTasks(tasks) {
  return tasks.map((task) => ({
    id: task.key,
    task_name: task.name || "unnamed",
    dependencies: dependencyList(task),
    status: "pending",
    retries: 0
  }));
}

export default function WorkflowBuilderPage({ workflowId, me, notify }) {
  const isEditing = Boolean(workflowId);
  const [workflow, setWorkflow] = useState(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [tasks, setTasks] = useState([createTask()]);
  const [loading, setLoading] = useState(isEditing);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState([]);
  const [pendingArchive, setPendingArchive] = useState(false);
  const [pendingRun, setPendingRun] = useState(false);
  const [schedules, setSchedules] = useState([]);
  const [scheduleCron, setScheduleCron] = useState("");
  const [scheduleInterval, setScheduleInterval] = useState("");

  const canEdit = me?.role === "operator" || me?.role === "admin";
  const canAdmin = me?.role === "admin";

  const load = useCallback(async () => {
    if (!workflowId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const data = await api.getWorkflow(workflowId);
      setWorkflow(data);
      setName(data.name);
      setDescription(data.description || "");
      setTasks(data.tasks.length ? workflowToTasks(data) : [createTask()]);
      const scheduleResult = await api.listSchedules(workflowId).catch(() => []);
      setSchedules(scheduleResult || []);
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  }, [workflowId]);

  useEffect(() => {
    load();
  }, [load]);

  const updateTask = (index, field, value) =>
    setTasks((current) => current.map((task, i) => (i === index ? { ...task, [field]: value } : task)));
  const addTask = () => setTasks((current) => [...current, createTask()]);
  const removeTask = (index) => setTasks((current) => current.filter((_, i) => i !== index));

  const errors = useMemo(() => validateTasks(tasks), [tasks]);

  const save = async (event) => {
    event.preventDefault();
    setError("");
    setFieldErrors(errors);
    if (errors.length) return;
    if (!name.trim()) {
      setFieldErrors(["Workflow name is required."]);
      return;
    }

    setSaving(true);
    const payload = { name: name.trim(), description: description.trim() || null, tasks: tasks.map(taskPayload) };
    try {
      if (isEditing) {
        const updated = await api.updateWorkflow(workflowId, payload);
        setWorkflow(updated);
        setTasks(workflowToTasks(updated));
        notify(`Saved revision r${updated.current_revision}.`, "success");
      } else {
        const created = await api.createWorkflow(payload);
        notify("Workflow created.", "success");
        navigate(pathFor.builder(created.id));
      }
    } catch (saveError) {
      setError(saveError.message);
      if (Array.isArray(saveError.details)) {
        setFieldErrors(saveError.details.map((detail) => `${(detail.loc || []).join(".")}: ${detail.msg}`));
      }
    } finally {
      setSaving(false);
    }
  };

  const run = async () => {
    if (!workflow) return;
    setRunning(true);
    try {
      const execution = await api.runWorkflow(workflow.id, crypto.randomUUID());
      notify("Execution started.", "success");
      navigate(pathFor.execution(execution.id));
    } catch (runError) {
      notify(runError.message, "error");
    } finally {
      setRunning(false);
    }
  };

  const archive = async () => {
    try {
      await api.deleteWorkflow(workflow.id);
      notify("Workflow archived.", "success");
      navigate(pathFor.workflows());
    } catch (archiveError) {
      notify(archiveError.message, "error");
    } finally {
      setPendingArchive(false);
    }
  };

  const addSchedule = async (event) => {
    event.preventDefault();
    const payload = scheduleCron.trim()
      ? { cron: scheduleCron.trim() }
      : scheduleInterval
        ? { interval_seconds: Number(scheduleInterval) }
        : null;
    if (!payload) {
      notify("Provide a cron expression or an interval.", "error");
      return;
    }
    try {
      const created = await api.createSchedule(workflow.id, payload);
      setSchedules((current) => [created, ...current]);
      setScheduleCron("");
      setScheduleInterval("");
      notify("Schedule created.", "success");
    } catch (scheduleError) {
      notify(scheduleError.message, "error");
    }
  };

  const deleteSchedule = async (scheduleId) => {
    try {
      await api.deleteSchedule(scheduleId);
      setSchedules((current) => current.filter((schedule) => schedule.id !== scheduleId));
      notify("Schedule removed.", "success");
    } catch (scheduleError) {
      notify(scheduleError.message, "error");
    }
  };

  if (loading) {
    return <div className="empty-state">Loading workflow…</div>;
  }

  if (error && !workflow && isEditing) {
    return <div className="error-text">{error}</div>;
  }

  return (
    <section className="builder-layout">
      <form className="panel builder-form" onSubmit={save}>
        <div className="page-heading">
          <div>
            <p className="eyebrow">{isEditing ? `Revision r${workflow?.current_revision}` : "New workflow"}</p>
            <h2>{isEditing ? "Edit workflow" : "Design a workflow"}</h2>
            <p className="muted">
              {isEditing
                ? "Saving creates an immutable revision. Running executions keep their original snapshot."
                : "Define the DAG, retry policy, and execution limits for each task."}
            </p>
          </div>
        </div>

        <label>
          Workflow name
          <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Nightly ingestion" required />
        </label>
        <label>
          Description
          <textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            rows={2}
            placeholder="What does this workflow do?"
          />
        </label>

        <div className="task-editor-list">
          {tasks.map((task, index) => (
            <fieldset key={task.key} className="task-editor">
              <legend>
                Task {index + 1}
                {task.name ? ` · ${task.name}` : ""}
              </legend>
              <div className="form-grid">
                <label>
                  Name
                  <input value={task.name} onChange={(event) => updateTask(index, "name", event.target.value)} placeholder="extract" required />
                </label>
                <label>
                  Dependencies
                  <input
                    value={task.dependencies}
                    onChange={(event) => updateTask(index, "dependencies", event.target.value)}
                    placeholder="comma separated task names"
                  />
                </label>
                <label>
                  Type
                  <select value={task.type} onChange={(event) => updateTask(index, "type", event.target.value)}>
                    {TASK_TYPES.map((type) => (
                      <option key={type.value} value={type.value}>
                        {type.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Duration (ms)
                  <input
                    type="number"
                    min="100"
                    max="300000"
                    value={task.duration_ms}
                    onChange={(event) => updateTask(index, "duration_ms", event.target.value)}
                  />
                </label>
                <label>
                  Max retries
                  <input
                    type="number"
                    min="0"
                    max="10"
                    value={task.max_retries}
                    onChange={(event) => updateTask(index, "max_retries", event.target.value)}
                  />
                </label>
                <label>
                  Fail first N runs
                  <input
                    type="number"
                    min="0"
                    max="10"
                    value={task.fail_first_n}
                    onChange={(event) => updateTask(index, "fail_first_n", event.target.value)}
                  />
                </label>
                <label>
                  Backoff (s)
                  <input
                    type="number"
                    min="0"
                    step="0.5"
                    value={task.backoff_seconds}
                    onChange={(event) => updateTask(index, "backoff_seconds", event.target.value)}
                  />
                </label>
                <label>
                  Start delay (s)
                  <input
                    type="number"
                    min="0"
                    step="0.5"
                    value={task.delay_seconds}
                    onChange={(event) => updateTask(index, "delay_seconds", event.target.value)}
                  />
                </label>
                <label>
                  Priority (0–100)
                  <input
                    type="number"
                    min="0"
                    max="100"
                    value={task.priority}
                    onChange={(event) => updateTask(index, "priority", event.target.value)}
                  />
                </label>
                <label>
                  Timeout (s)
                  <input
                    type="number"
                    min="1"
                    max="86400"
                    value={task.timeout_seconds}
                    onChange={(event) => updateTask(index, "timeout_seconds", event.target.value)}
                  />
                </label>
                <label className="checkbox-field">
                  <input
                    type="checkbox"
                    checked={task.allow_failure}
                    onChange={(event) => updateTask(index, "allow_failure", event.target.checked)}
                  />
                  Allow failure (downstream continues)
                </label>
              </div>

              {task.type === "http" ? (
                <div className="form-grid">
                  <label>
                    Method
                    <select value={task.method} onChange={(event) => updateTask(index, "method", event.target.value)}>
                      {["GET", "POST", "PUT", "PATCH", "DELETE"].map((method) => (
                        <option key={method} value={method}>
                          {method}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    URL
                    <input value={task.url} onChange={(event) => updateTask(index, "url", event.target.value)} placeholder="https://example.com" />
                  </label>
                  <label>
                    Expected status
                    <input
                      type="number"
                      min="100"
                      max="599"
                      value={task.expected_status}
                      onChange={(event) => updateTask(index, "expected_status", event.target.value)}
                      placeholder="200"
                    />
                  </label>
                  <label>
                    Body
                    <input value={task.body} onChange={(event) => updateTask(index, "body", event.target.value)} placeholder='{"hello":"world"}' />
                  </label>
                  <label className="span-2">
                    Headers (JSON)
                    <textarea
                      rows={2}
                      value={task.headersText}
                      onChange={(event) => updateTask(index, "headersText", event.target.value)}
                      placeholder='{"Authorization":"Bearer {{secret:api_token}}"}'
                    />
                  </label>
                </div>
              ) : null}

              {task.type === "echo" ? (
                <label>
                  Message
                  <input value={task.message} onChange={(event) => updateTask(index, "message", event.target.value)} placeholder="Workflow finished." />
                </label>
              ) : null}

              <div className="form-actions">
                <button type="button" className="danger-text-button" onClick={() => removeTask(index)} disabled={tasks.length === 1}>
                  Remove task
                </button>
              </div>
            </fieldset>
          ))}
        </div>

        <div className="form-actions sticky-actions">
          <button type="button" className="secondary-button" onClick={addTask}>
            Add task
          </button>
          <div className="button-row">
            {isEditing && canAdmin ? (
              <button type="button" className="danger-text-button" onClick={() => setPendingArchive(true)}>
                Archive
              </button>
            ) : null}
            {isEditing ? (
              <button type="button" className="secondary-button" onClick={() => setPendingRun(true)} disabled={running}>
                {running ? "Starting…" : "Run workflow"}
              </button>
            ) : null}
            <button type="submit" disabled={saving || !canEdit}>
              {saving ? "Saving…" : isEditing ? "Save revision" : "Create workflow"}
            </button>
          </div>
        </div>

        {!canEdit ? <p className="hint">Your viewer key can inspect workflows but not change them.</p> : null}
        {fieldErrors.length ? (
          <ul className="error-list" role="alert">
            {fieldErrors.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : null}
        {error ? (
          <p className="error-text" role="alert">
            {error}
          </p>
        ) : null}
      </form>

      <aside className="builder-aside">
        <div className="panel">
          <div className="panel-heading">
            <h3>DAG preview</h3>
            <p className="muted">Arrows show dependency order.</p>
          </div>
          <TaskGraph tasks={previewTasks(tasks)} />
        </div>

        {isEditing ? (
          <div className="panel">
            <div className="panel-heading">
              <h3>Schedules</h3>
              <p className="muted">Cron or fixed interval triggers.</p>
            </div>
            <form className="stack compact" onSubmit={addSchedule}>
              <label>
                Cron
                <input value={scheduleCron} onChange={(event) => setScheduleCron(event.target.value)} placeholder="0 2 * * *" />
              </label>
              <label>
                Interval (seconds)
                <input
                  type="number"
                  min="10"
                  value={scheduleInterval}
                  onChange={(event) => setScheduleInterval(event.target.value)}
                  placeholder="3600"
                />
              </label>
              <button type="submit" className="secondary-button" disabled={!canEdit}>
                Add schedule
              </button>
            </form>
            <ul className="list">
              {schedules.map((schedule) => (
                <li key={schedule.id} className="list-row">
                  <div>
                    <strong>{schedule.cron ? `Cron ${schedule.cron}` : `Every ${schedule.interval_seconds}s`}</strong>
                    <span className="muted">Next: {formatDate(schedule.next_run_at)}</span>
                  </div>
                  <button className="danger-text-button" onClick={() => deleteSchedule(schedule.id)} disabled={!canEdit}>
                    Remove
                  </button>
                </li>
              ))}
              {!schedules.length ? <li className="muted">No schedules configured.</li> : null}
            </ul>
          </div>
        ) : null}

        <div className="panel">
          <div className="panel-heading">
            <h3>Revisions</h3>
          </div>
          {workflow ? (
            <p className="muted">
              Current revision r{workflow.current_revision}. Created {formatDate(workflow.created_at)}. Every save stores an
              immutable revision used by new executions.
            </p>
          ) : (
            <p className="muted">Save the workflow to start tracking revisions.</p>
          )}
        </div>
      </aside>

      <ConfirmDialog
        open={pendingArchive}
        title="Archive workflow?"
        description="Archived workflows can’t run, but their executions and revisions are preserved."
        confirmLabel="Archive"
        onCancel={() => setPendingArchive(false)}
        onConfirm={archive}
      />

      <ConfirmDialog
        open={pendingRun}
        title="Run this workflow?"
        description={
          workflow
            ? `This starts a new execution from revision r${workflow.current_revision}. Unsaved edits are not included.`
            : ""
        }
        confirmLabel="Start run"
        onCancel={() => setPendingRun(false)}
        onConfirm={() => {
          setPendingRun(false);
          run();
        }}
      />
    </section>
  );
}
