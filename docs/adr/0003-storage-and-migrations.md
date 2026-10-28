# ADR 0003: PostgreSQL in production, SQLite for local loop, Alembic for schema

- Status: Accepted
- Date: 2026-10-29
- Decision owners: Anish Kumar

## Context

The engine depends on row locking, `SKIP LOCKED`, and concurrent readers and writers.
Local development should not require infrastructure. Schema changes must be reviewable
and roll forward safely during deploys.

## Decision

- **Production:** PostgreSQL 16 with async SQLAlchemy (`asyncpg`), configurable pool size,
  overflow, and pool timeout. `SKIP LOCKED` claims and `ON DELETE CASCADE` constraints are
  used in the hot path.
- **Local development and tests:** SQLite through `aiosqlite` with WAL, busy timeout, and
  foreign key pragmas. Tests run against an in-memory database with `StaticPool`, except
  the Postgres integration test, which runs in CI against a real server.
- **Schema:** SQLAlchemy models are the source of truth, and Alembic owns deployment
  changes. The baseline revision creates the schema; every subsequent change gets a new
  revision. Production runs `alembic upgrade head` as a release job (a Compose `migrate`
  service or a Kubernetes pre-sync Job). `DEVFLOW_AUTO_MIGRATE` is rejected in production
  so a rolling deployment never races migrations.
- Timestamps are stored as naive UTC datetimes for cross-dialect consistency; the API
  serializes them as UTC.

## Consequences

- SQLite remains usable for one developer and the test suite but is not a production
  target; it serializes writers and lacks `SKIP LOCKED`.
- The baseline revision calls `create_all` once. New revisions must use explicit Alembic
  operations so they are reviewable and reversible.
- Backup, restore, and point-in-time recovery are PostgreSQL responsibilities (see
  `docs/RUNBOOK.md`).

## Alternatives considered

- **SQLite only:** no operational database, but no safe concurrent workers.
- **Auto-create schema at startup:** convenient, but racing replicas and unreviewed
  changes make rollbacks unreliable.
