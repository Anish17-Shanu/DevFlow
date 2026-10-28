# Architecture decision records

| ID | Decision | Status |
| --- | --- | --- |
| [0001](0001-database-backed-queue.md) | Database-backed queue instead of a dedicated broker | Accepted |
| [0002](0002-realtime-websocket.md) | WebSocket updates with polling fallback | Accepted |
| [0003](0003-storage-and-migrations.md) | PostgreSQL production, SQLite local, Alembic migrations | Accepted |

Add a new record for decisions that change a public contract, a datastore, or an
operational guarantee. Keep records immutable once accepted; supersede them with a new
ADR instead of rewriting history.
