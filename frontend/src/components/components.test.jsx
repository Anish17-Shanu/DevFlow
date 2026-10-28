import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ConfirmDialog from "../components/ConfirmDialog.jsx";
import ErrorBoundary from "../components/ErrorBoundary.jsx";
import StatusPill from "../components/StatusPill.jsx";
import TaskGraph from "../components/TaskGraph.jsx";

describe("StatusPill", () => {
  it("renders a friendly label for known statuses", () => {
    render(<StatusPill status="success" />);
    expect(screen.getByText("Succeeded")).toBeInTheDocument();
    expect(screen.getByTitle("Succeeded")).toHaveClass("status-pill", "success");
  });

  it("accepts a custom label and unknown statuses", () => {
    render(<StatusPill status="custom" label="Custom state" />);
    expect(screen.getByText("Custom state")).toBeInTheDocument();
  });
});

describe("ConfirmDialog", () => {
  it("renders nothing while closed", () => {
    const { container } = render(<ConfirmDialog open={false} title="Confirm" onCancel={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("focuses cancel and handles escape and confirm", () => {
    const onCancel = vi.fn();
    const onConfirm = vi.fn();
    render(
      <ConfirmDialog
        open
        title="Run workflow?"
        description="This starts a new execution."
        confirmLabel="Run now"
        onCancel={onCancel}
        onConfirm={onConfirm}
      />
    );

    expect(screen.getByRole("dialog", { name: "Run workflow?" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();

    fireEvent.keyDown(window, { key: "Escape" });
    expect(onCancel).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Run now" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});

describe("TaskGraph", () => {
  const tasks = [
    { id: "1", task_name: "extract", status: "success", dependencies: [] },
    { id: "2", task_name: "load", status: "queued", dependencies: ["extract"] }
  ];

  it("shows an empty state before tasks exist", () => {
    render(<TaskGraph tasks={[]} />);
    expect(screen.getByText(/No task state yet/)).toBeInTheDocument();
  });

  it("draws nodes and dependency edges", () => {
    render(<TaskGraph tasks={tasks} />);

    expect(screen.getByRole("img", { name: "Execution task dependency graph" })).toBeInTheDocument();
    expect(screen.getByLabelText("extract: success")).toBeInTheDocument();
    expect(screen.getByLabelText("load: queued")).toBeInTheDocument();
    expect(document.querySelectorAll("path")).toHaveLength(2);
  });

  it("selects nodes by click and keyboard", () => {
    const onSelectTask = vi.fn();
    render(<TaskGraph tasks={tasks} onSelectTask={onSelectTask} />);

    fireEvent.click(screen.getByLabelText("load: queued"));
    expect(onSelectTask).toHaveBeenCalledWith(tasks[1]);

    fireEvent.keyDown(screen.getByLabelText("extract: success"), { key: "Enter" });
    expect(onSelectTask).toHaveBeenCalledWith(tasks[0]);
  });
});

describe("ErrorBoundary", () => {
  function Exploding() {
    throw new Error("boom");
  }

  it("catches render errors and offers recovery", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <ErrorBoundary>
        <Exploding />
      </ErrorBoundary>
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong");
    expect(screen.getByRole("alert")).toHaveTextContent("boom");
    expect(screen.getByRole("button", { name: "Reload DevFlow" })).toBeInTheDocument();
    spy.mockRestore();
  });
});
