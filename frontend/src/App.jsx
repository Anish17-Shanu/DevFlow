import { useCallback, useEffect, useRef, useState } from "react";

import Header from "./components/Header";
import ExecutionDetailPage from "./pages/ExecutionDetailPage";
import ExecutionsPage from "./pages/ExecutionsPage";
import LoginPage from "./pages/LoginPage";
import MonitorPage from "./pages/MonitorPage";
import OperationsPage from "./pages/OperationsPage";
import WorkflowBuilderPage from "./pages/WorkflowBuilderPage";
import WorkflowsPage from "./pages/WorkflowsPage";
import { useHashRoute } from "./lib/router";
import { api, auth } from "./services/api";

export default function App() {
  const route = useHashRoute();
  const [me, setMe] = useState(null);
  const [booting, setBooting] = useState(true);
  const [authError, setAuthError] = useState("");
  const [health, setHealth] = useState(null);
  const [readiness, setReadiness] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [toast, setToast] = useState(null);
  const toastTimer = useRef(null);

  const notify = useCallback((message, tone = "info") => {
    setToast({ message, tone });
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 5000);
  }, []);

  const loadHealth = useCallback(async () => {
    const [healthResult, readinessResult] = await Promise.allSettled([api.getHealth(), api.getReadiness()]);
    if (healthResult.status === "fulfilled") setHealth(healthResult.value);
    if (readinessResult.status === "fulfilled") setReadiness(readinessResult.value);
  }, []);

  useEffect(() => {
    const boot = async () => {
      if (!auth.hasKey()) {
        setBooting(false);
        return;
      }
      try {
        setMe(await api.me());
      } catch (error) {
        auth.clearKey();
        setAuthError(error.status === 401 ? "Your session expired. Sign in again." : error.message);
      } finally {
        setBooting(false);
      }
    };
    boot();
    loadHealth();
  }, [loadHealth]);

  useEffect(() => {
    const interval = setInterval(() => {
      if (document.visibilityState === "visible") loadHealth();
    }, 15000);
    return () => clearInterval(interval);
  }, [loadHealth]);

  useEffect(() => {
    const onUnauthorized = () => {
      if (!me) return;
      auth.clearKey();
      setMe(null);
      setAuthError("Your API key is no longer valid. Sign in again.");
    };
    window.addEventListener("devflow:unauthorized", onUnauthorized);
    return () => window.removeEventListener("devflow:unauthorized", onUnauthorized);
  }, [me]);

  const logout = () => {
    auth.clearKey();
    setMe(null);
    setAuthError("");
    setToast(null);
    window.location.hash = "#/workflows";
  };

  const refresh = async () => {
    setRefreshing(true);
    await loadHealth();
    setRefreshing(false);
    notify("Runtime status refreshed.", "success");
  };

  if (booting) {
    return <div className="boot-screen">Starting DevFlow…</div>;
  }

  if (!me) {
    return (
      <LoginPage
        initialError={authError}
        onAuthenticated={(principal) => {
          setMe(principal);
          setAuthError("");
          if (!window.location.hash || window.location.hash === "#/") {
            window.location.hash = "#/workflows";
          }
        }}
      />
    );
  }

  const [section, param, sub] = route.segments;
  const isBuilder = section === "workflows" && (param === "new" || sub === "edit");
  const sectionName = section || "workflows";

  let page = null;
  if (sectionName === "workflows") {
    page = isBuilder ? (
      <WorkflowBuilderPage workflowId={param === "new" ? "" : param} me={me} notify={notify} />
    ) : (
      <WorkflowsPage me={me} notify={notify} />
    );
  } else if (sectionName === "executions") {
    page = param ? (
      <ExecutionDetailPage executionId={param} me={me} notify={notify} />
    ) : (
      <ExecutionsPage routeQuery={route.query} notify={notify} />
    );
  } else if (sectionName === "monitor") {
    page = <MonitorPage me={me} />;
  } else if (sectionName === "operations") {
    page =
      me.role === "admin" ? (
        <OperationsPage notify={notify} />
      ) : (
        <div className="empty-state">Operations require an admin key.</div>
      );
  } else {
    page = (
      <div className="empty-state">
        Page not found. <a href="#/workflows">Go to workflows</a>.
      </div>
    );
  }

  return (
    <div className="app-shell">
      <Header
        routeName={isBuilder ? "builder" : sectionName}
        me={me}
        health={health}
        readiness={readiness}
        onRefresh={refresh}
        isRefreshing={refreshing}
        onLogout={logout}
      />
      {page}
      {toast ? (
        <div className={`toast ${toast.tone}`} role="status" onClick={() => setToast(null)}>
          {toast.message}
        </div>
      ) : null}
    </div>
  );
}
