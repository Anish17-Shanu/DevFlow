import { describe, expect, it } from "vitest";

import { formatDate, formatDuration, formatRelative, shortId } from "../lib/format.js";

describe("format helpers", () => {
  it("renders placeholders for missing values", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatRelative(undefined)).toBe("—");
    expect(formatDuration(null)).toBe("—");
    expect(shortId("")).toBe("—");
  });

  it("formats UTC timestamps from the API", () => {
    const value = "2026-10-29T12:00:00";
    expect(formatDate(value)).not.toBe(value);
    expect(formatDate(value)).toContain("2026");
  });

  it("describes relative times", () => {
    expect(formatRelative(new Date(Date.now() - 1000).toISOString())).toBe("just now");
    expect(formatRelative(new Date(Date.now() - 30_000).toISOString())).toBe("30s ago");
    expect(formatRelative(new Date(Date.now() - 5 * 60_000).toISOString())).toBe("5m ago");
    expect(formatRelative(new Date(Date.now() - 3 * 3600_000).toISOString())).toBe("3h ago");
    expect(formatRelative(new Date(Date.now() - 2 * 86400_000).toISOString())).toBe("2d ago");
  });

  it("formats durations across units", () => {
    const now = new Date();
    expect(formatDuration(now.toISOString(), new Date(now.getTime() + 300).toISOString())).toBe("300ms");
    expect(formatDuration(now.toISOString(), new Date(now.getTime() + 2500).toISOString())).toBe("2.5s");
    expect(formatDuration(now.toISOString(), new Date(now.getTime() + 125_000).toISOString())).toBe("2m 5s");
    expect(formatDuration(now.toISOString())).toMatch(/ms|s/);
  });

  it("shortens identifiers", () => {
    expect(shortId("1234567890abcdef")).toBe("12345678");
  });
});
