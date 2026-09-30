# Cohort Insights API

FastAPI + MongoDB + Redis take-home implementation.

## Stack

- Python 3.11
- FastAPI
- MongoDB
- Redis
- Docker Compose
- pytest

## Run

```bash
docker compose up --build
```

API: http://localhost:8000

Health:

```bash
curl http://localhost:8000/health
```

Interactive API documentation:

`/docs`

## API

### Submit

`POST /documents`

```json
{
  "user_id": "user-1",
  "title": "FastAPI",
  "content": "FastAPI is a Python web framework.",
  "client_doc_ref": "partner-100"
}
```

### Poll

`GET /documents/{document_id}?user_id=user-1`

### Update

`PATCH /documents/{document_id}`

```json
{
  "content": "Updated content"
}
```

### User listing

`GET /users/{user_id}/documents?page=1&page_size=20`

Optional `status` filter is supported.

### Crosswalk

`GET /documents/by-ref/{client_doc_ref}`

## Crosswalk decision

`client_doc_ref` is optional and unique.

- Same ref + same content: idempotent; return the existing document.
- Same ref + different content: HTTP 409 Conflict.
- The lookup uses a unique sparse MongoDB index on `client_doc_ref`.

This avoids ambiguous ownership of an external identifier and makes retries safe.

## Schema & Staleness Design

Each document has:

- `content`
- `content_hash`
- `content_version`
- `processing.content_version`
- `enriching.content_version`

Every PATCH increments `content_version`, replaces the content/hash, and resets both stages.

A worker captures the version when it starts. Every result write contains an atomic MongoDB predicate:

```text
_id == document_id AND content_version == worker_version
```

Therefore an old worker cannot overwrite a newer PATCHed version.

A reader only exposes `summary` and `tags` if:

```text
processing.content_version == document.content_version
AND
enriching.content_version == document.content_version
AND
both stages are completed
```

This makes the mixed-version result unobservable. A stale stage may physically exist during a race, but the API will not return it as the current result.

## Pipeline

```text
queued
  -> processing
  -> enriching
  -> completed
```

Each stage has an independent simulated failure probability of approximately 10%.

If enriching fails, processing remains completed. The document records the failing stage rather than using ad-hoc status strings.

Job claiming uses an atomic MongoDB `find_one_and_update`, so two workers cannot both successfully claim the same queued document.

## Redis

Redis has two separate concerns.

### Active pipeline limit

Each user has a Redis counter:

```text
active-documents:{user_id}
```

A Lua script atomically checks the current count and increments only if it is below 3.

The counter is released when the pipeline reaches a terminal state.

### Content cache

Cache keys are based on content hash:

```text
content-result:{sha256}
```

They are never based on `document_id`.

Consequently, PATCHing a document to new content cannot accidentally reuse the old document's cache entry.

Redis failures should be treated as infrastructure failures rather than silently bypassing the concurrency guarantee.

## Ownership

Document GET by ID requires the submitting `user_id`. The database query is:

```text
_id + user_id
```

A non-owner receives 404, avoiding confirmation that another user's document exists.

The external `by-ref` endpoint is intentionally a partner lookup and therefore is not an owner-scoped endpoint in this example. In a real authenticated deployment, partner authorization would be required.

## At 100×

At 100× traffic, the `(user_id, created_at)` index remains useful for user listings because MongoDB can seek directly to a user's index range rather than scanning the whole collection. However, a user with 500K documents creates a large contiguous index range and can become a concentrated read workload. If a few tenants are much larger than the rest, simply choosing `user_id` as a shard key can also create an uneven distribution or a hot shard.

For horizontal MongoDB scaling, I would separate the logical query key from the physical shard key. A hashed high-cardinality document identifier is a candidate for distributing writes evenly, while a supporting `(user_id, created_at, _id)` index handles user-oriented reads. The trade-off is that some user queries may become scatter-gather operations depending on the final shard-key design. If tenant isolation and predictable routing were more important, a compound strategy based on tenant/user plus a hashed component would be evaluated against the real workload.

The Redis active-job counter uses an atomic Lua script, so a single reservation cannot be lost to a GET/INCR race. At 100× submit QPS, I would add Redis connection pooling, latency/error monitoring, HA/replication, and careful TTL/recovery handling. If a user's traffic becomes extremely hot, a single Redis key for that user can itself become a concentrated operation stream; sharding Redis or changing the concurrency-control design may then be appropriate.

Skip/limit pagination is acceptable for small offsets but becomes increasingly expensive for deep pages because the database must advance through skipped records. I would move the listing API to cursor/keyset pagination using `(created_at, _id)` as a stable ordering key. The client sends the last item from the previous page as a cursor, and the next query seeks directly after that position. This keeps page traversal much more stable as a user's document count grows.

## Production improvements with more time

- Move workers into a separate deployment/process instead of running one worker inside the API container.
- Add durable queue semantics and retry/backoff.
- Add optimistic concurrency tokens to PATCH requests.
- Add cursor pagination.
- Add authentication/JWT rather than accepting user_id as a query parameter.
- Add structured JSON logging and tracing.
- Add Prometheus metrics.
- Add integration tests against real MongoDB/Redis containers.
- Add worker lease/recovery for crashes after job claim.
- Add explicit idempotency keys for POST.
- Add MongoDB transaction/outbox patterns if publishing to an external queue.
