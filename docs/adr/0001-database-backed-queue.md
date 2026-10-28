# ADR 0001: Database-backed queue instead of a dedicated broker

- Status: Accepted
- Date: 2026-10-29
- Decision owners: Anish Kumar

## Context

DevFlow needs durable task queuing, at-least-once delivery, retries, delayed jobs, and
operator visibility. The workload is workflow orchestration: hundreds of tasks per
minute, not millions of messages per second. Adding Redis, SQS, or Kafka would introduce
a second stateful system to back up, secure, and monitor alongside PostgreSQL.

## Decision

Use the existing PostgreSQL database as the queue (`queue_jobs`). Claim work with
`SELECT ... FOR UPDATE SKIP LOCKED` on PostgreSQL so multiple workers never lease the same
job. SQLite uses an equivalent single-writer transaction for local development. Jobs
carry leases with expiry, attempts, priority, delayed availability, and a dead-letter
state. A watchdog requeues expired leases and dead-letters poison jobs. The queue is
behind `DatabaseJobQueue`, so another backend can be added later without changing
services.

## Consequences

- One database is the source of truth for workflows, executions, logs, and queue state.
- Transactions can atomically write business state and enqueue follow-up work.
- Queue throughput is bounded by PostgreSQL write capacity; every claim is an `UPDATE`.
- Polling replaces broker push. Workers poll at a configurable interval, and per-workflow
  concurrency is enforced with a correlated count in the claim query.
- Cross-region and very high throughput scenarios will need partitioning (see ROADMAP
  SCALE-03/05) or a dedicated broker.

## Alternatives considered

- **Redis + RQ/Celery:** fast, but a second datastore, weaker durability guarantees by
  default, and separate monitoring/backup procedures.
- **SQS:** managed durability, but vendor lock-in, no transactional enqueue with business
  writes, and per-message costs that are hard to predict for task fan-out.
- **Kafka:** excellent throughput and replay, disproportionate operational cost for a
  workflow engine at this scale.
