import { useMemo } from "react";

const NODE_WIDTH = 190;
const NODE_HEIGHT = 66;
const H_GAP = 88;
const V_GAP = 26;
const PADDING = 20;

const STATUS_FILL = {
  success: "#d7f0df",
  failed: "#f6d8d5",
  cancelled: "#ececec",
  running: "#f6e6c8",
  queued: "#dbe5f8",
  pending: "#eef0ef",
  retrying: "#f2e0cb",
  skipped: "#e8e5f0"
};

const STATUS_STROKE = {
  success: "#2f8a55",
  failed: "#b13f2e",
  cancelled: "#8a8a8a",
  running: "#b3760f",
  queued: "#3a5fa8",
  pending: "#8a9994",
  retrying: "#b3760f",
  skipped: "#6b5b95"
};

function buildLayout(tasks) {
  const depth = new Map();
  const byName = new Map(tasks.map((task) => [task.task_name, task]));

  const resolveDepth = (name, visiting = new Set()) => {
    if (depth.has(name)) return depth.get(name);
    if (visiting.has(name)) return 0;
    visiting.add(name);
    const task = byName.get(name);
    const dependencies = (task?.dependencies || []).filter((dependency) => byName.has(dependency));
    const value = dependencies.length ? Math.max(...dependencies.map((dep) => resolveDepth(dep, visiting) + 1)) : 0;
    depth.set(name, value);
    return value;
  };

  tasks.forEach((task) => resolveDepth(task.task_name));

  const columns = new Map();
  tasks.forEach((task) => {
    const column = depth.get(task.task_name) || 0;
    if (!columns.has(column)) columns.set(column, []);
    columns.get(column).push(task);
  });

  const positions = new Map();
  let maxRows = 0;
  columns.forEach((items, column) => {
    items.forEach((task, row) => {
      positions.set(task.task_name, {
        x: PADDING + column * (NODE_WIDTH + H_GAP),
        y: PADDING + row * (NODE_HEIGHT + V_GAP),
        column,
        row
      });
    });
    maxRows = Math.max(maxRows, items.length);
  });

  const width = PADDING * 2 + Math.max(1, columns.size) * NODE_WIDTH + Math.max(0, columns.size - 1) * H_GAP;
  const height = PADDING * 2 + Math.max(1, maxRows) * NODE_HEIGHT + Math.max(0, maxRows - 1) * V_GAP;

  return { positions, width, height };
}

export default function TaskGraph({ tasks = [], selectedTask, onSelectTask }) {
  const { positions, width, height } = useMemo(() => buildLayout(tasks), [tasks]);
  const edges = useMemo(
    () =>
      tasks.flatMap((task) =>
        (task.dependencies || [])
          .filter((dependency) => positions.has(dependency))
          .map((dependency) => ({ from: dependency, to: task.task_name }))
      ),
    [tasks, positions]
  );

  if (!tasks.length) {
    return <div className="empty-state">No task state yet. Start an execution to see the graph.</div>;
  }

  return (
    <div className="task-graph-scroll">
      <svg
        className="task-graph-svg"
        viewBox={`0 0 ${width} ${height}`}
        width={width}
        height={height}
        role="img"
        aria-label="Execution task dependency graph"
      >
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#9aa8a3" />
          </marker>
        </defs>
        {edges.map(({ from, to }) => {
          const source = positions.get(from);
          const target = positions.get(to);
          if (!source || !target) return null;
          const x1 = source.x + NODE_WIDTH;
          const y1 = source.y + NODE_HEIGHT / 2;
          const x2 = target.x;
          const y2 = target.y + NODE_HEIGHT / 2;
          const midX = (x1 + x2) / 2;
          return (
            <path
              key={`${from}-${to}`}
              d={`M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`}
              fill="none"
              stroke="#9aa8a3"
              strokeWidth="2"
              markerEnd="url(#arrow)"
            />
          );
        })}
        {tasks.map((task) => {
          const position = positions.get(task.task_name);
          if (!position) return null;
          const selected = selectedTask === task.task_name;
          const isInteractive = Boolean(onSelectTask);
          return (
            <g
              key={task.id || task.task_name}
              transform={`translate(${position.x}, ${position.y})`}
              className={`graph-node${isInteractive ? " interactive" : ""}`}
              role={isInteractive ? "button" : undefined}
              tabIndex={isInteractive ? 0 : undefined}
              aria-label={`${task.task_name}: ${task.status}`}
              onClick={() => isInteractive && onSelectTask(task)}
              onKeyDown={(event) => {
                if (isInteractive && (event.key === "Enter" || event.key === " ")) {
                  event.preventDefault();
                  onSelectTask(task);
                }
              }}
            >
              <rect
                width={NODE_WIDTH}
                height={NODE_HEIGHT}
                rx="14"
                fill={STATUS_FILL[task.status] || "#eef0ef"}
                stroke={selected ? "#0d6b61" : STATUS_STROKE[task.status] || "#8a9994"}
                strokeWidth={selected ? 3 : 1.5}
              />
              <text x="14" y="27" className="graph-node-title">
                {task.task_name.length > 22 ? `${task.task_name.slice(0, 21)}…` : task.task_name}
              </text>
              <text x="14" y="48" className="graph-node-status">
                {task.status}
                {task.retries ? ` · retry ${task.retries}` : ""}
              </text>
              <title>{`${task.task_name} — ${task.status}${task.error_message ? ` — ${task.error_message}` : ""}`}</title>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
