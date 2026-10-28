from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter(
    "devflow_http_requests_total",
    "HTTP requests processed.",
    ["method", "path", "status"],
)
HTTP_LATENCY = Histogram(
    "devflow_http_request_duration_seconds",
    "HTTP request latency.",
    ["method", "path"],
)
EXECUTIONS = Counter(
    "devflow_executions_total",
    "Workflow executions by terminal status.",
    ["status"],
)
TASKS = Counter(
    "devflow_tasks_total",
    "Task executions by terminal status.",
    ["status"],
)
TASK_DURATION = Histogram(
    "devflow_task_duration_seconds",
    "Task execution duration.",
    ["status"],
)
TASK_WAIT = Histogram(
    "devflow_task_wait_seconds",
    "Time a task waited in the queue before a worker claimed it.",
)
QUEUE_DEPTH = Gauge("devflow_queue_depth", "Queued jobs ready to run.")
QUEUE_DELAYED = Gauge("devflow_queue_delayed", "Delayed jobs.")
QUEUE_IN_FLIGHT = Gauge("devflow_queue_in_flight", "Leased jobs.")
QUEUE_DEAD_LETTER = Gauge("devflow_queue_dead_letter", "Terminal queue failures.")
WORKERS_ONLINE = Gauge("devflow_workers_online", "Workers with a fresh heartbeat.")
