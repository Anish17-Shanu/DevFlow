import { useState } from "react";

const createEmptyTask = () => ({ name: "", dependencies: "", duration_ms: 1000, max_retries: 0, fail_first_n: 0 });

export default function WorkflowBuilderPage({ workflows, onCreateWorkflow, onRunWorkflow, lastExecutionId }) {
  const [name, setName] = useState("");
  const [tasks, setTasks] = useState([createEmptyTask()]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const updateTask = (index, field, value) => {
    setTasks((current) => current.map((task, i) => (i === index ? { ...task, [field]: value } : task)));
  };

  const addTask = () => setTasks((current) => [...current, createEmptyTask()]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSubmitting(true);
    setError("");

    try {
      await onCreateWorkflow({
        name,
        tasks: tasks.map((task) => ({
          name: task.name,
          dependencies: task.dependencies
            .split(",")
            .map((item) => item.trim())
            .filter(Boolean),
          config: {
            duration_ms: Number(task.duration_ms),
            max_retries: Number(task.max_retries),
            fail_first_n: Number(task.fail_first_n)
          }
        }))
      });
      setName("");
      setTasks([createEmptyTask()]);
    } catch (submitError) {
      setError(submitError.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="page-grid">
      <div className="panel panel-form">
        <div className="panel-heading">
          <h2>Design a workflow DAG</h2>
          <p>Define task topology, retry policy, and simulated runtime behavior.</p>
        </div>
        <form className="workflow-form" onSubmit={handleSubmit}>
          <label>
            Workflow name
            <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Nightly ingestion" required />
          </label>
          <div className="task-editor-list">
            {tasks.map((task, index) => (
              <div key={`${index}-${task.name}`} className="task-editor">
                <label>
                  Task name
                  <input
                    value={task.name}
                    onChange={(event) => updateTask(index, "name", event.target.value)}
                    placeholder="extract"
                    required
                  />
                </label>
                <label>
                  Dependencies
                  <input
                    value={task.dependencies}
                    onChange={(event) => updateTask(index, "dependencies", event.target.value)}
                    placeholder="extract, validate"
                  />
                </label>
                <label>
                  Duration ms
                  <input
                    type="number"
                    min="100"
                    value={task.duration_ms}
                    onChange={(event) => updateTask(index, "duration_ms", event.target.value)}
                  />
                </label>
                <label>
                  Max retries
                  <input
                    type="number"
                    min="0"
                    value={task.max_retries}
                    onChange={(event) => updateTask(index, "max_retries", event.target.value)}
                  />
                </label>
                <label>
                  Fail first N runs
                  <input
                    type="number"
                    min="0"
                    value={task.fail_first_n}
                    onChange={(event) => updateTask(index, "fail_first_n", event.target.value)}
                  />
                </label>
              </div>
            ))}
          </div>
          <div className="form-actions">
            <button type="button" className="secondary-button" onClick={addTask}>
              Add Task
            </button>
            <button type="submit" disabled={submitting}>
              {submitting ? "Creating..." : "Create Workflow"}
            </button>
          </div>
          {error ? <p className="error-text">{error}</p> : null}
        </form>
      </div>

      <div className="panel">
        <div className="panel-heading">
          <h2>Available workflows</h2>
          <p>Seeded pipelines plus anything created through the builder.</p>
        </div>
        <div className="workflow-list">
          {workflows.map((workflow) => (
            <article key={workflow.id} className="workflow-card">
              <div>
                <strong>{workflow.name}</strong>
                <span>{workflow.tasks.length} tasks</span>
              </div>
              <button onClick={() => onRunWorkflow(workflow.id)}>Run workflow</button>
            </article>
          ))}
        </div>
        {lastExecutionId ? <p className="success-text">Latest execution started: {lastExecutionId}</p> : null}
      </div>
    </section>
  );
}
