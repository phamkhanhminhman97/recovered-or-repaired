# order-service

Order processing service: HTTP API + background worker (BullMQ) on Postgres and Redis.

- API: `POST /orders`, `POST /deposits`, `POST /transfers`, `POST /notifications`,
  `GET /accounts/:id/statement`, `GET /catalog/items`, `GET /catalog/search`, `GET /health`, `GET /metrics`
- Writes are queued and processed by the worker (`src/worker.js`); failed jobs go to the `jobs-dlq` queue
  after 3 attempts.
- Payments, notifications and pricing are provided by the partner API (`PARTNER_API_URL`).
- Configuration lives in `.env`; previous configuration releases are kept in `releases/`.
- Database migrations in `db/migrations` run at startup.

Run: `docker compose up -d --build` · logs: `docker compose logs app` · DB: `docker compose exec postgres psql -U app`
