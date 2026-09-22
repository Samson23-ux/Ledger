# Ledger

A wallet and payments backend built on FastAPI, with Paystack as the payment processor. It handles wallet funding (card and bank transfer), refunds, and webhook-driven reconciliation, with an emphasis on the async payments correctness problems that are easy to get wrong: idempotent requests under real concurrency, exactly-once side effects, and safe recovery from partial failures.

## What it does

- **Auth** — email/password signup with OTP verification, Google OAuth, JWT access/refresh tokens.
- **Wallets** — one wallet per user, funded via Paystack (card, with saved-card auto-charge on repeat funding, or bank transfer), with a running credit/debit ledger (`wallet_credits`).
- **Transactions & refunds** — full lifecycle tracking with an append-only state-event audit trail (`transaction_state_events`, `refund_state_events`), refund requests, and a retry path for refunds stuck in `needs_attention`.
- **Webhooks** — HMAC-SHA512 signature verification over the raw request body, with deduplication so the same Paystack event can never be double-processed.
- **Reconciliation** — scheduled jobs that poll Paystack directly for any transaction/refund still pending past a grace period, only touching rows whose status has actually diverged from what Paystack reports.

## Architecture notes

A few things worth knowing before touching the payment-flow code:

- **Outbox pattern.** Anything that needs to call Paystack from a background job (charge authorization, refund requests, webhook forwarding) writes an `outbox` row in the same DB transaction as its triggering change, then dispatches a Celery task. A separate poller (`outbox_task`, on a schedule) sweeps any row still `pending` past its grace period, so a crashed or lost task still gets retried without ever running twice. A Redis lock keyed per-resource keeps the original task and the poller from double-executing the same row.
- **Idempotent wallet funding.** `POST /wallets/me/fund` uses `INSERT ... ON CONFLICT (idempotency_key) DO UPDATE ... RETURNING` as the arbitration point for concurrent duplicate requests. Postgres itself blocks a second concurrent insert on the same key until the first transaction resolves, so two requests racing on the same idempotency key are guaranteed to call Paystack exactly once — no distributed lock needed for this specific path.
- **Shared circuit breaker.** A Redis-backed circuit breaker (`paystack:circuit`) sits in front of every Paystack call, both from the API and from Celery tasks, sharing one key, a run of failures from either side trips the same breaker, and further attempts reject immediately instead of hammering a known-down dependency.
- **Dead-letter queue.** Rejected tasks dead-letter into `ledger.dlq`. Since Celery only declares a queue on the broker when some worker actually consumes it, and nothing should auto-consume dead-lettered tasks, a one-shot `ledger_declare_queues` service declares the DLQ (and every other queue) without subscribing to it.

## Tech stack

FastAPI · SQLAlchemy 2.0 (async) · PostgreSQL · Redis · Celery + RabbitMQ · Alembic · Paystack · Argon2 (`pwdlib`) · JWT (`python-jose`) · Sentry · pytest

## Getting started

Requires Docker and Docker Compose.

1. Copy `.env` with the required variables (see below) into the project root.
2. Start everything:

   ```bash
   docker compose up -d
   ```

   This brings up Postgres, Redis, RabbitMQ, runs Alembic migrations (`ledger_migrate`), declares the outbox/DLQ queues (`ledger_declare_queues`), then starts the API, the Celery worker, the Celery beat scheduler, and the reconciliation/outbox worker.

3. The API is available at `http://localhost:8000`, docs at `http://localhost:8000/docs`.
4. `ledger_ngrok` exposes a public URL for Paystack webhooks to reach your local instance during development — configure `NGROK_DOMAIN`/`NGROK_AUTHTOKEN` and point your Paystack webhook URL at it.

### Environment variables

| Variable | Purpose |
|---|---|
| `ASYNC_DB_URL` / `SYNC_DB_URL` | Postgres connection strings (asyncpg for the API, psycopg2 for Celery workers) |
| `ASYNC_TEST_DB_URL` | Postgres connection string for the test suite |
| `REDIS_URL` | Redis (locks, idempotency keys, circuit breaker, rate limiting, Celery result backend) |
| `BROKER_URL` | RabbitMQ (Celery broker) |
| `PAYSTACK_API_KEY` | Paystack secret key |
| `ARGON2_PASSWORD_PEPPER` | Pepper mixed into password hashing |
| `ACCESS_TOKEN_SECRET_KEY` / `REFRESH_TOKEN_SECRET_KEY` | JWT signing keys |
| `SESSION_SECRET_KEY` | Signs the OAuth session cookie |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google OAuth |
| `SENTRY_SDK_DSN` | Error/performance monitoring |
| `API_EMAIL` / `RESEND_API_KEY` | Transactional email via Resend |
| `NGROK_AUTHTOKEN` / `NGROK_DOMAIN` / `NGROK_URL` | Local webhook tunnel |

## Running tests

Tests run against a real Postgres and Redis (not mocked), using the `ASYNC_TEST_DB_URL` database:

```bash
docker compose up -d ledger_postgres ledger_redis
python -m pytest test/ -q
```

Most tests isolate each other with a savepoint-per-test rollback. The concurrency tests (`test_failure_modes.py`) deliberately use real, committed connections instead, since testing genuine cross-connection database locking requires connections that aren't sharing one transaction.

## API overview

All routes are prefixed with `/api/v1`.

**Auth**
| Method | Path | |
|---|---|---|
| POST | `/auth/signup` | Sign up with email + password |
| GET | `/auth/google` | Start Google OAuth |
| GET | `/auth/google/callback` | Google OAuth redirect target |
| PATCH | `/auth/verify` | Verify account with an OTP code |
| POST | `/auth/verify/resend` | Resend the verification code |
| POST | `/auth/login` | Log in |
| POST | `/auth/refresh` | Exchange a refresh token for a new access token |
| GET | `/auth/me` | Current user |
| POST | `/auth/logout` | Log out |
| DELETE | `/auth` | Delete account permanently |

**Wallets**
| Method | Path | |
|---|---|---|
| GET | `/wallets/me` | Current user's wallet |
| GET | `/wallets/me/credits` | Wallet credit ledger (paginated) |
| GET | `/wallets/me/credits/{id}` | A single wallet credit record |
| POST | `/wallets/me/fund` | Fund the wallet (returns a Paystack checkout redirect, or the transaction directly for a saved-card auto-charge) |
| GET | `/wallets/fund/callback` | Paystack redirects here after checkout |

**Transactions & refunds**
| Method | Path | |
|---|---|---|
| GET | `/transactions` | List transactions (paginated) |
| GET | `/transactions/{id}` | A single transaction |
| GET | `/transactions/{id}/events` | A transaction's state-change history |
| POST | `/transactions/{id}/refunds` | Request a refund for a successful transaction |
| GET | `/transactions/refunds` | List refunds (paginated) |
| GET | `/transactions/refunds/{id}` | A single refund |
| GET | `/transactions/refunds/{id}/events` | A refund's state-change history |
| POST | `/transactions/refunds/{id}/details` | Supply bank account details to retry a refund stuck in `needs_attention` |

**Webhooks**
| Method | Path | |
|---|---|---|
| POST | `/webhooks/paystack` | Paystack event ingress |
