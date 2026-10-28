import { useCallback, useEffect, useMemo, useState } from "react";

import ConfirmDialog from "../components/ConfirmDialog";
import EmptyState from "../components/EmptyState";
import StatusPill from "../components/StatusPill";
import { formatDate, formatRelative, shortId } from "../lib/format";
import { navigate, pathFor } from "../lib/router";
import { api } from "../services/api";

export default function WorkflowsPage({ me, notify }) {
  const [workflows, setWorkflows] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(null);
  const [pendingRun, setPendingRun] = useState(null);
  const [busyId, setBusyId] = useState("");

  const canOperate = me?.role === "operator" || me?.role === "admin";
  const canAdmin = me?.role === "admin";

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [workflowResult, templateResult] = await Promise.allSettled([
        api.listWorkflows({ limit: 200, include_archived: includeArchived }),
        api.listTemplates()
      ]);
      if (workflowResult.status === "rejected") throw workflowResult.reason;
      setWorkflows(workflowResult.value.items || []);
      if (templateResult.status === "fulfilled") setTemplates(templateResult.value || []);
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  }, [includeArchived]);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return workflows;
    return workflows.filter(
      (workflow) =>
        workflow.name.toLowerCase().includes(term) ||
        (workflow.description || "").toLowerCase().includes(term)
    );
  }, [workflows, search]);

  const run = async (workflow) => {
    setBusyId(workflow.id);
    try {
      const execution = await api.runWorkflow(workflow.id, crypto.randomUUID());
      notify(`Started “${workflow.name}”.`, "success");
      navigate(pathFor.execution(execution.id));
    } catch (runError) {
      notify(runError.message, "error");
    } finally {
      setBusyId("");
    }
  };

  const clone = async (workflow) => {
    setBusyId(workflow.id);
    try {
      const copy = await api.cloneWorkflow(workflow.id, `${workflow.name} (copy)`);
      setWorkflows((current) => [copy, ...current]);
      notify("Workflow cloned.", "success");
    } catch (cloneError) {
      notify(cloneError.message, "error");
    } finally {
      setBusyId("");
    }
  };

  const remove = async () => {
    if (!pendingDelete) return;
    setBusyId(pendingDelete.id);
    try {
      await api.deleteWorkflow(pendingDelete.id);
      setWorkflows((current) => current.filter((workflow) => workflow.id !== pendingDelete.id));
      notify("Workflow archived.", "success");
    } catch (deleteError) {
      notify(deleteError.message, "error");
    } finally {
      setBusyId("");
      setPendingDelete(null);
    }
  };

  const useTemplate = async (template) => {
    setBusyId(template.name);
    try {
      const created = await api.createWorkflow({
        name: template.name,
        description: template.description,
        tasks: template.tasks
      });
      notify("Workflow created from template.", "success");
      navigate(pathFor.builder(created.id));
    } catch (templateError) {
      notify(templateError.message, "error");
    } finally {
      setBusyId("");
    }
  };

  return (
    <section className="page-stack">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Library</p>
          <h2>Workflows</h2>
          <p className="muted">Versioned DAG definitions with immutable revisions and reproducible snapshots.</p>
        </div>
        {canOperate ? (
          <a className="button-link" href={`#/${pathFor.builder()}`}>
            New workflow
          </a>
        ) : null}
      </div>

      <div className="toolbar">
        <label className="inline-field">
          <span>Search</span>
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Filter by name or description"
          />
        </label>
        <label className="checkbox-field">
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(event) => setIncludeArchived(event.target.checked)}
          />
          Include archived
        </label>
        <button className="secondary-button" onClick={load} disabled={loading}>
          {loading ? "Loading…" : "Reload"}
        </button>
      </div>

      {error ? (
        <div className="error-text" role="alert">
          {error}
        </div>
      ) : null}

      {loading && !workflows.length ? <div className="skeleton-list" aria-label="Loading workflows" /> : null}

      {!loading && !filtered.length ? (
        <EmptyState
          title={search ? "No workflows match your search" : "No workflows yet"}
          description={search ? "Try a different term." : "Create a workflow or start from a template below."}
        />
      ) : null}

      <div className="card-grid">
        {filtered.map((workflow) => (
          <article key={workflow.id} className="workflow-card">
            <div className="workflow-card-body">
              <div className="workflow-card-title">
                <h3>{workflow.name}</h3>
                {workflow.is_archived ? <StatusPill status="cancelled" label="Archived" /> : <StatusPill status="success" label="Active" />}
              </div>
              <p className="muted clamp-2">{workflow.description || "No description provided."}</p>
              <dl className="inline-meta">
                <div>
                  <dt>Tasks</dt>
                  <dd>{workflow.tasks.length}</dd>
                </div>
                <div>
                  <dt>Revision</dt>
                  <dd>r{workflow.current_revision}</dd>
                </div>
                <div>
                  <dt>Updated</dt>
                  <dd title={formatDate(workflow.updated_at)}>{formatRelative(workflow.updated_at)}</dd>
                </div>
                <div>
                  <dt>ID</dt>
                  <dd>
                    <code>{shortId(workflow.id)}</code>
                  </dd>
                </div>
              </dl>
            </div>
            <div className="workflow-card-actions">
              <a className="ghost-button" href={`#/executions?workflow=${workflow.id}`}>
                Runs
              </a>
              {canOperate ? (
                <>
                  <a className="ghost-button" href={`#/${pathFor.builder(workflow.id)}`}>
                    Edit
                  </a>
                  <button className="secondary-button" onClick={() => clone(workflow)} disabled={busyId === workflow.id}>
                    Clone
                  </button>
                  <button onClick={() => setPendingRun(workflow)} disabled={busyId === workflow.id || workflow.is_archived}>
                    {busyId === workflow.id ? "Working…" : "Run"}
                  </button>
                </>
              ) : null}
              {canAdmin && !workflow.is_archived ? (
                <button className="danger-text-button" onClick={() => setPendingDelete(workflow)}>
                  Archive
                </button>
              ) : null}
            </div>
          </article>
        ))}
      </div>

      {templates.length && canOperate ? (
        <div className="panel">
          <div className="panel-heading">
            <h2>Start from a template</h2>
            <p>Templates create a new editable workflow with proven task configuration.</p>
          </div>
          <div className="template-grid">
            {templates.map((template) => (
              <article key={template.name} className="template-card">
                <h3>{template.name}</h3>
                <p className="muted">{template.description}</p>
                <p className="hint">{template.tasks.length} tasks</p>
                <button className="secondary-button" onClick={() => useTemplate(template)} disabled={busyId === template.name}>
                  Use template
                </button>
              </article>
            ))}
          </div>
        </div>
      ) : null}

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="Archive workflow?"
        description={
          pendingDelete
            ? `“${pendingDelete.name}” will be archived. Existing runs stay available and the workflow can’t be executed until restored.`
            : ""
        }
        confirmLabel="Archive workflow"
        onCancel={() => setPendingDelete(null)}
        onConfirm={remove}
      />

      <ConfirmDialog
        open={Boolean(pendingRun)}
        title="Start a new run?"
        description={
          pendingRun
            ? `“${pendingRun.name}” will start a new execution using revision r${pendingRun.current_revision}. Runs consume worker capacity.`
            : ""
        }
        confirmLabel="Start run"
        onCancel={() => setPendingRun(null)}
        onConfirm={() => {
          const target = pendingRun;
          setPendingRun(null);
          if (target) run(target);
        }}
      />
    </section>
  );
}
