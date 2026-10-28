# ADR 0002: WebSocket updates with a polling fallback

- Status: Accepted
- Date: 2026-10-29
- Decision owners: Anish Kumar

## Context

Operators watch executions while workers update task state and append logs. Polling alone
adds latency and load; a mail-shot WebSocket alone is fragile behind proxies and during
deploys. The API also scales horizontally, so in-process fan-out does not reach clients
connected to another replica.

## Decision

1. The API exposes `GET /ws/executions/{execution_id}?api_key=...`. The socket is
   authenticated and authorized for one execution; unknown executions and cross-tenant
   access close with code `1008`.
2. The `RealtimeService` fans out events to sockets connected to the same API process.
   The notifier reads the transactional outbox and also polls execution state.
3. The UI always runs a polling fallback (3 s on the execution page, 5 s on lists) and
   reconnects with exponential backoff after a drop.

## Consequences

- Single-replica deployments receive near-instant updates.
- Multi-replica deployments may deliver an event to only the replica that owns the
  socket; the polling fallback keeps the UI correct, at the cost of latency.
- Moving fan-out to Redis pub/sub or PostgreSQL `LISTEN/NOTIFY` is the documented path
  for consistent multi-replica delivery (ROADMAP SCALE-02).
- WebSocket API keys appear in query strings, so access logs must redact query strings
  at the proxy, and keys should be short-lived where possible.

## Alternatives considered

- **Server-Sent Events:** simpler proxying, but no client-to-server subscription message
  and similar multi-replica fan-out work.
- **Pure polling:** simplest, but higher latency and database load at scale.
