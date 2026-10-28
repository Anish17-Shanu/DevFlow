import { useEffect, useState } from "react";

export function parseHash(hash) {
  const clean = hash.replace(/^#\/?/, "");
  const [pathPart, searchPart] = clean.split("?");
  const segments = pathPart.split("/").filter(Boolean);
  return {
    segments,
    name: segments[0] || "workflows",
    param: segments[1] || "",
    query: new URLSearchParams(searchPart || "")
  };
}

export function navigate(path) {
  const target = `#/${path.replace(/^\/?#?\/?/, "")}`;
  if (window.location.hash === target) {
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    return;
  }
  window.location.hash = target;
}

export function useHashRoute() {
  const [route, setRoute] = useState(() => parseHash(window.location.hash));

  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  return route;
}

export const pathFor = {
  workflows: () => "workflows",
  builder: (id = "") => (id ? `workflows/${id}/edit` : "workflows/new"),
  executions: () => "executions",
  execution: (id) => `executions/${id}`,
  monitor: () => "monitor",
  operations: () => "operations"
};
