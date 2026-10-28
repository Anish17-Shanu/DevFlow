import { describe, expect, it } from "vitest";

import { navigate, parseHash, pathFor } from "../lib/router.js";

describe("hash router", () => {
  it("defaults to the workflows page", () => {
    const route = parseHash("");
    expect(route.name).toBe("workflows");
    expect(route.param).toBe("");
    expect(route.segments).toEqual([]);
  });

  it("parses nested paths and query strings", () => {
    const route = parseHash("#/executions/abc-123?status=failed&limit=25");
    expect(route.name).toBe("executions");
    expect(route.param).toBe("abc-123");
    expect(route.query.get("status")).toBe("failed");
    expect(route.query.get("limit")).toBe("25");
  });

  it("ignores leading slashes", () => {
    expect(parseHash("#/monitor").name).toBe("monitor");
    expect(parseHash("#operations").name).toBe("operations");
  });

  it("builds canonical paths", () => {
    expect(pathFor.workflows()).toBe("workflows");
    expect(pathFor.builder()).toBe("workflows/new");
    expect(pathFor.builder("wf-1")).toBe("workflows/wf-1/edit");
    expect(pathFor.execution("exec-1")).toBe("executions/exec-1");
    expect(pathFor.monitor()).toBe("monitor");
    expect(pathFor.operations()).toBe("operations");
  });

  it("navigates by setting the hash", () => {
    navigate("executions/abc");
    expect(window.location.hash).toBe("#/executions/abc");
  });
});
