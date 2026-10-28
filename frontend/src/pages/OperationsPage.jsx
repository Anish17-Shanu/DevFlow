import { useCallback, useEffect, useState } from "react";

import EmptyState from "../components/EmptyState";
import StatusPill from "../components/StatusPill";
import { formatDate, formatRelative, shortId } from "../lib/format";
import { api } from "../services/api";

const TABS = [
  { id: "audit", label: "Audit log" },
  { id: "keys", label: "API keys" },
  { id: "secrets", label: "Secrets" },
  { id: "webhooks", label: "Webhooks" },
  { id: "dead-letters", label: "Dead letters" }
];

export default function OperationsPage({ notify }) {
  const [tab, setTab] = useState("audit");

  return (
    <section className="page-stack">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Administration</p>
          <h2>Operations</h2>
          <p className="muted">Audit trail, access keys, encrypted secrets, webhook deliveries, and poison-message recovery.</p>
        </div>
      </div>

      <div className="tab-bar" role="tablist" aria-label="Operations sections">
        {TABS.map((item) => (
          <button
            key={item.id}
            role="tab"
            aria-selected={tab === item.id}
            className={tab === item.id ? "tab active" : "tab"}
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>

      {tab === "audit" ? <AuditPanel /> : null}
      {tab === "keys" ? <KeysPanel notify={notify} /> : null}
      {tab === "secrets" ? <SecretsPanel notify={notify} /> : null}
      {tab === "webhooks" ? <WebhooksPanel notify={notify} /> : null}
      {tab === "dead-letters" ? <DeadLettersPanel notify={notify} /> : null}
    </section>
  );
}

function useLoader(loader) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await loader());
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  }, [loader]);

  useEffect(() => {
    load();
  }, [load]);

  return { data, error, loading, reload: load, setData };
}

function AuditPanel() {
  const loader = useCallback(() => api.auditLog({ limit: 100 }), []);
  const { data, error, loading, reload } = useLoader(loader);

  return (
    <div className="panel">
      <div className="panel-heading">
        <h3>Audit log</h3>
        <p className="muted">Every privileged action is recorded with actor, resource, and request context.</p>
      </div>
      <button className="secondary-button" onClick={reload} disabled={loading}>
        {loading ? "Loading…" : "Reload"}
      </button>
      {error ? <p className="error-text">{error}</p> : null}
      {data?.items?.length ? (
        <div className="table-wrap">
          <table className="data-table compact">
            <thead>
              <tr>
                <th scope="col">When</th>
                <th scope="col">Actor</th>
                <th scope="col">Action</th>
                <th scope="col">Resource</th>
                <th scope="col">Details</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((entry) => (
                <tr key={entry.id}>
                  <td className="muted" title={formatDate(entry.created_at)}>
                    {formatRelative(entry.created_at)}
                  </td>
                  <td>{entry.actor_label}</td>
                  <td>
                    <code>{entry.action}</code>
                  </td>
                  <td className="mono-small">
                    {entry.resource_type}/{shortId(entry.resource_id)}
                  </td>
                  <td className="muted small">{JSON.stringify(entry.details)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState title={loading ? "Loading audit entries…" : "No audit entries yet"} />
      )}
    </div>
  );
}

function KeysPanel({ notify }) {
  const loader = useCallback(() => api.listApiKeys(), []);
  const { data, error, loading, reload } = useLoader(loader);
  const [name, setName] = useState("");
  const [role, setRole] = useState("viewer");
  const [createdKey, setCreatedKey] = useState(null);

  const create = async (event) => {
    event.preventDefault();
    try {
      const result = await api.createApiKey({ name, role });
      setCreatedKey(result);
      setName("");
      notify("API key created. Copy it now — it is shown once.", "success");
      reload();
    } catch (createError) {
      notify(createError.message, "error");
    }
  };

  const revoke = async (keyId) => {
    try {
      await api.revokeApiKey(keyId);
      notify("API key revoked.", "success");
      reload();
    } catch (revokeError) {
      notify(revokeError.message, "error");
    }
  };

  return (
    <div className="panel">
      <div className="panel-heading">
        <h3>API keys</h3>
        <p className="muted">Keys are hashed at rest. The raw value is only returned once.</p>
      </div>
      <form className="toolbar" onSubmit={create}>
        <label className="inline-field">
          <span>Name</span>
          <input value={name} onChange={(event) => setName(event.target.value)} placeholder="ci-runner" required />
        </label>
        <label className="inline-field">
          <span>Role</span>
          <select value={role} onChange={(event) => setRole(event.target.value)}>
            <option value="viewer">viewer</option>
            <option value="operator">operator</option>
            <option value="admin">admin</option>
          </select>
        </label>
        <button type="submit">Create key</button>
      </form>
      {createdKey ? (
        <div className="success-text">
          <strong>{createdKey.name}</strong> — copy this key now:
          <code className="key-value">{createdKey.key}</code>
        </div>
      ) : null}
      {error ? <p className="error-text">{error}</p> : null}
      {data?.length ? (
        <div className="table-wrap">
          <table className="data-table compact">
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Prefix</th>
                <th scope="col">Role</th>
                <th scope="col">Created</th>
                <th scope="col">Last used</th>
                <th scope="col">Status</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {data.map((key) => (
                <tr key={key.id}>
                  <td>{key.name}</td>
                  <td>
                    <code>{key.prefix}…</code>
                  </td>
                  <td>{key.role}</td>
                  <td className="muted">{formatRelative(key.created_at)}</td>
                  <td className="muted">{key.last_used_at ? formatRelative(key.last_used_at) : "never"}</td>
                  <td>
                    <StatusPill status={key.revoked_at ? "cancelled" : "success"} label={key.revoked_at ? "Revoked" : "Active"} />
                  </td>
                  <td>
                    {!key.revoked_at ? (
                      <button className="small danger-text-button" onClick={() => revoke(key.id)}>
                        Revoke
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState title={loading ? "Loading keys…" : "No API keys"} />
      )}
    </div>
  );
}

function SecretsPanel({ notify }) {
  const loader = useCallback(() => api.listSecrets(), []);
  const { data, error, loading, reload } = useLoader(loader);
  const [name, setName] = useState("");
  const [value, setValue] = useState("");

  const create = async (event) => {
    event.preventDefault();
    try {
      await api.createSecret({ name, value });
      setName("");
      setValue("");
      notify("Secret stored.", "success");
      reload();
    } catch (createError) {
      notify(createError.message, "error");
    }
  };

  const remove = async (secretName) => {
    try {
      await api.deleteSecret(secretName);
      notify("Secret deleted.", "success");
      reload();
    } catch (deleteError) {
      notify(deleteError.message, "error");
    }
  };

  return (
    <div className="panel">
      <div className="panel-heading">
        <h3>Secrets</h3>
        <p className="muted">
          Encrypted with Fernet. Reference them in HTTP tasks as <code>{"{{secret:name}}"}</code>.
        </p>
      </div>
      <form className="toolbar" onSubmit={create}>
        <label className="inline-field">
          <span>Name</span>
          <input value={name} onChange={(event) => setName(event.target.value)} placeholder="api_token" required />
        </label>
        <label className="inline-field grow">
          <span>Value</span>
          <input type="password" value={value} onChange={(event) => setValue(event.target.value)} required />
        </label>
        <button type="submit">Store secret</button>
      </form>
      {error ? <p className="error-text">{error}</p> : null}
      {data?.length ? (
        <ul className="list">
          {data.map((secret) => (
            <li key={secret.id} className="list-row">
              <div>
                <strong>{secret.name}</strong>
                <span className="muted">Updated {formatDate(secret.updated_at)}</span>
              </div>
              <button className="danger-text-button" onClick={() => remove(secret.name)}>
                Delete
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState title={loading ? "Loading secrets…" : "No secrets stored"} />
      )}
    </div>
  );
}

function WebhooksPanel({ notify }) {
  const loader = useCallback(async () => {
    const [endpoints, deliveries] = await Promise.all([api.listWebhooks(), api.listDeliveries({ limit: 25 })]);
    return { endpoints, deliveries };
  }, []);
  const { data, error, loading, reload } = useLoader(loader);
  const [url, setUrl] = useState("");
  const [secret, setSecret] = useState("");
  const [events, setEvents] = useState(["execution.succeeded", "execution.failed"]);

  const create = async (event) => {
    event.preventDefault();
    try {
      await api.createWebhook({ url, secret, events });
      setUrl("");
      setSecret("");
      notify("Webhook created.", "success");
      reload();
    } catch (createError) {
      notify(createError.message, "error");
    }
  };

  const remove = async (id) => {
    try {
      await api.deleteWebhook(id);
      notify("Webhook removed.", "success");
      reload();
    } catch (deleteError) {
      notify(deleteError.message, "error");
    }
  };

  const toggleEvent = (eventName) =>
    setEvents((current) =>
      current.includes(eventName) ? current.filter((item) => item !== eventName) : [...current, eventName]
    );

  return (
    <div className="panel">
      <div className="panel-heading">
        <h3>Webhooks</h3>
        <p className="muted">Signed with HMAC-SHA256 and retried with backoff.</p>
      </div>
      <form className="stack compact" onSubmit={create}>
        <label>
          Endpoint URL
          <input value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://hooks.example.com/devflow" required />
        </label>
        <label>
          Signing secret (min 16 chars)
          <input type="password" value={secret} onChange={(event) => setSecret(event.target.value)} minLength={16} required />
        </label>
        <div className="checkbox-row">
          {["execution.started", "execution.succeeded", "execution.failed", "execution.cancelled"].map((eventName) => (
            <label key={eventName} className="checkbox-field">
              <input type="checkbox" checked={events.includes(eventName)} onChange={() => toggleEvent(eventName)} />
              {eventName}
            </label>
          ))}
        </div>
        <button type="submit">Add webhook</button>
      </form>
      {error ? <p className="error-text">{error}</p> : null}
      {data?.endpoints?.length ? (
        <ul className="list">
          {data.endpoints.map((endpoint) => (
            <li key={endpoint.id} className="list-row">
              <div>
                <strong className="mono-small">{endpoint.url}</strong>
                <span className="muted small">{endpoint.events.join(", ")}</span>
              </div>
              <button className="danger-text-button" onClick={() => remove(endpoint.id)}>
                Remove
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState title={loading ? "Loading webhooks…" : "No webhooks configured"} />
      )}
      {data?.deliveries?.items?.length ? (
        <>
          <div className="panel-heading">
            <h4>Recent deliveries</h4>
          </div>
          <div className="table-wrap">
            <table className="data-table compact">
              <thead>
                <tr>
                  <th scope="col">Event</th>
                  <th scope="col">Status</th>
                  <th scope="col">Attempts</th>
                  <th scope="col">Next attempt</th>
                  <th scope="col">Last error</th>
                </tr>
              </thead>
              <tbody>
                {data.deliveries.items.map((delivery) => (
                  <tr key={delivery.id}>
                    <td>{delivery.event_type}</td>
                    <td>
                      <StatusPill status={delivery.status} />
                    </td>
                    <td>{delivery.attempts}</td>
                    <td className="muted">{formatRelative(delivery.next_attempt_at)}</td>
                    <td className="muted small">{delivery.last_error || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
    </div>
  );
}

function DeadLettersPanel({ notify }) {
  const loader = useCallback(() => api.listDeadLetters({ limit: 100 }), []);
  const { data, error, loading, reload } = useLoader(loader);

  const replay = async (jobId) => {
    try {
      await api.replayDeadLetter(jobId);
      notify("Dead letter replayed.", "success");
      reload();
    } catch (replayError) {
      notify(replayError.message, "error");
    }
  };

  return (
    <div className="panel">
      <div className="panel-heading">
        <h3>Dead letters</h3>
        <p className="muted">Jobs that exhausted retries. Replay after fixing the root cause.</p>
      </div>
      <button className="secondary-button" onClick={reload} disabled={loading}>
        {loading ? "Loading…" : "Reload"}
      </button>
      {error ? <p className="error-text">{error}</p> : null}
      {data?.items?.length ? (
        <div className="table-wrap">
          <table className="data-table compact">
            <thead>
              <tr>
                <th scope="col">Job</th>
                <th scope="col">Execution</th>
                <th scope="col">Attempts</th>
                <th scope="col">Error</th>
                <th scope="col">Created</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((job) => (
                <tr key={job.id}>
                  <td className="mono-small">{shortId(job.id)}</td>
                  <td className="mono-small">{shortId(job.execution_id)}</td>
                  <td>{job.attempts}</td>
                  <td className="muted small">{job.last_error || "—"}</td>
                  <td className="muted">{formatRelative(job.created_at)}</td>
                  <td>
                    <button className="small secondary-button" onClick={() => replay(job.id)}>
                      Replay
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState title={loading ? "Loading dead letters…" : "No dead letters"} description="Nothing is stuck in the poison queue." />
      )}
    </div>
  );
}
