import { beforeEach, describe, expect, it, vi } from "vitest";

async function loadApi({ key = "" } = {}) {
  localStorage.clear();
  if (key) {
    localStorage.setItem("devflow.apiKey", key);
  }
  vi.resetModules();
  return import("../services/api.js");
}

function jsonResponse(body, { status = 200, headers = {} } = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(headers),
    json: async () => body
  };
}

describe("api client", () => {
  beforeEach(() => {
    global.fetch = vi.fn();
  });

  it("sends the stored API key on requests", async () => {
    const { api } = await loadApi({ key: "dvf_secret" });
    global.fetch.mockResolvedValue(jsonResponse({ tenant_id: "t", role: "viewer" }));

    await api.me();

    expect(global.fetch).toHaveBeenCalledTimes(1);
    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toBe("/api/v1/auth/me");
    expect(options.headers["X-API-Key"]).toBe("dvf_secret");
    expect(options.headers.Accept).toBe("application/json");
  });

  it("attaches idempotency keys when running workflows", async () => {
    const { api } = await loadApi({ key: "dvf_secret" });
    global.fetch.mockResolvedValue(jsonResponse({ id: "exec-1" }));

    await api.runWorkflow("wf-1", "idem-9");

    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toBe("/api/v1/workflows/wf-1/run");
    expect(options.method).toBe("POST");
    expect(options.headers["Idempotency-Key"]).toBe("idem-9");
  });

  it("serializes JSON bodies", async () => {
    const { api } = await loadApi({ key: "dvf_secret" });
    global.fetch.mockResolvedValue(jsonResponse({ id: "wf-1" }, { status: 201 }));

    await api.createWorkflow({ name: "flow", tasks: [{ name: "one" }] });

    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toBe("/api/v1/workflows");
    expect(options.method).toBe("POST");
    expect(options.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(options.body).name).toBe("flow");
  });

  it("treats 204 responses as empty", async () => {
    const { api } = await loadApi({ key: "dvf_secret" });
    global.fetch.mockResolvedValue(jsonResponse(null, { status: 204 }));

    await expect(api.revokeApiKey("key-1")).resolves.toBeNull();
  });

  it("maps structured API errors and emits unauthorized events", async () => {
    const { api, ApiError } = await loadApi({ key: "dvf_secret" });
    global.fetch.mockResolvedValue(
      jsonResponse(
        {
          code: "unauthorized",
          message: "Invalid API key.",
          request_id: "req-123",
          details: [{ loc: ["header"] }]
        },
        { status: 401 }
      )
    );
    const listener = vi.fn();
    window.addEventListener("devflow:unauthorized", listener);

    const error = await api.me().catch((caught) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(401);
    expect(error.code).toBe("unauthorized");
    expect(error.requestId).toBe("req-123");
    expect(error.details).toHaveLength(1);
    expect(listener).toHaveBeenCalledTimes(1);
    window.removeEventListener("devflow:unauthorized", listener);
  });

  it("falls back to the X-Request-ID header", async () => {
    const { api } = await loadApi({ key: "dvf_secret" });
    global.fetch.mockResolvedValue(
      jsonResponse({ detail: "Not found." }, { status: 404, headers: { "X-Request-ID": "header-req" } })
    );

    const error = await api.getWorkflow("missing").catch((caught) => caught);
    expect(error.requestId).toBe("header-req");
    expect(error.message).toBe("Not found.");
  });

  it("translates network failures into a friendly error", async () => {
    const { api } = await loadApi({ key: "dvf_secret" });
    global.fetch.mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(api.me()).rejects.toThrow(/Cannot reach the DevFlow API/);
  });

  it("uses the API root for health probes", async () => {
    const { api } = await loadApi();
    global.fetch.mockResolvedValue(jsonResponse({ status: "ok" }));

    await api.getHealth();

    expect(global.fetch.mock.calls[0][0]).toBe("/health");
  });
});
