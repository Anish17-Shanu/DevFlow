import { useState } from "react";

import { api, auth } from "../services/api";

export default function LoginPage({ onAuthenticated, initialError }) {
  const [key, setKey] = useState(auth.getKey());
  const [error, setError] = useState(initialError || "");
  const [busy, setBusy] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    auth.setKey(key);
    try {
      const me = await api.me();
      onAuthenticated(me);
    } catch (loginError) {
      auth.clearKey();
      setError(loginError.status === 401 ? "That API key was rejected." : loginError.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="login-shell">
      <section className="login-card">
        <p className="eyebrow">Distributed workflow engine · built by Anish Kumar</p>
        <h1>Sign in to DevFlow</h1>
        <p className="muted">
          DevFlow uses scoped API keys. Paste a key with the <code>viewer</code>, <code>operator</code>, or{" "}
          <code>admin</code> role to continue.
        </p>
        <form onSubmit={submit} className="stack">
          <label htmlFor="api-key">
            API key
            <input
              id="api-key"
              type="password"
              autoComplete="off"
              value={key}
              onChange={(event) => setKey(event.target.value)}
              placeholder="dv_..."
              required
              autoFocus
            />
          </label>
          <button type="submit" disabled={busy || !key.trim()}>
            {busy ? "Verifying…" : "Continue"}
          </button>
        </form>
        {error ? (
          <p className="error-text" role="alert">
            {error}
          </p>
        ) : null}
        <p className="hint">
          In development the bootstrap key defaults to <code>devflow-dev-key</code>. Production deployments set{" "}
          <code>DEVFLOW_BOOTSTRAP_API_KEY</code>.
        </p>
      </section>
    </main>
  );
}
