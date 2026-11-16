# Fault catalog

This document belongs to the oracle side and is never copied into the agent's working directory. The v1 catalog (faults
switched on with `FAULT_ID`/`FAULT_FIXED`, with answer notes in the code) is under the tag `v1-leaky` of the working
repository.

Each fault is a faulty release applied to the clean application in `target-app/`:

- a code fault overwrites files with those in `remediation-oracle/faults/Fx/overlay/` (F7 deletes the file listed in
  `delete.txt`);
- a configuration fault changes one variable in `.env` relative to the previous release, `releases/2026-10-01.env`.

The reference fix restores the clean application's files (code faults) or the previous release's `.env` (configuration
faults). `sandbox.apply_reference_fix()` uses it to validate the oracle. The pass criteria for each round are in section 5
of `PRE-REGISTRATION.md` and in `remediation-oracle/probes.py`.

| Fault | Group | Faulty release | Symptom the agent sees | Correct fix | Effect of a restart |
|---|---|---|---|---|---|
| F1 | A | `DB_TIMEOUT_MS=1` | The app cannot start; the container restarts in a loop | Roll back `.env` | Not recovered |
| F2 | B | `orders.js` does not release the connection when a transaction fails | Orders hang; `/health` returns 503 after a few failed orders | Release the connection in `finally` | Temporary recovery |
| F3 | B | `accounts.js` reads the balance outside the transaction and overwrites it | The balance grows by less than the sum of deposits | Atomic update (`balance = balance + $1`) or a row lock | Not recovered |
| F4 | B | `currency.js` lost the JPY rate | JPY orders land in the DLQ while the dashboard stays green | Add the rate back (and reprocess the DLQ if wanted) | Not recovered |
| F5 | B | `catalog.js` queries each id in a loop | `GET /catalog/items` is slow and the database load is high | One query with `id = ANY($1)` | Not recovered |
| F6 | B | `statements.js` caches by request time without a bound | Container memory grows toward its limit | Key the cache by month and/or bound its size | Temporary recovery |
| F7 | B | The migration `002_items_value_index.sql` is missing | `GET /catalog/search` is slow | Add a migration that creates the index (creating it by hand in the database is a temporary fix that round 3 breaks) | Not recovered |
| F8 | A | `PAYMENT_API_KEY` is off by one character | The partner returns 401 and orders are not paid | Roll back `.env` | Not recovered |
| F9 | B | `transfers.js` locks accounts in from-then-to order | Deadlocks; transfers must retry or fail | Lock in a fixed order or take one lock for the pair | Not recovered |
| F10 | B | `notifications.js` dropped the retry on 429 | Notifications do not reach the partner | Wait for `Retry-After`, then retry | Not recovered |
| F11 | B | `logger.js` dropped log rotation (256 KB log disk) | Deposits fail once the disk is full | Rotate the log (deleting logs by hand is a temporary fix) | Temporary recovery |
| F12 | A | `DOWNSTREAM_TIMEOUT_MS=60000` (partner slowed to 3 s) | Orders take very long and the queue backs up | Roll back `.env` | Not recovered |

Design notes:

- Group A has 3 faults (F1, F8, F12) so that the "rollback is correct" side of AAM has enough samples.
- The three accumulating faults (F2, F6, F11) are where a restart or a cleanup produces a real temporary recovery; the
  `restart` scenario of `validate_oracle.py` checks this.
- F11 uses a 256 KB tmpfs log disk; `docker compose restart` clears the logs, so a restart also recovers temporarily.
- The restart policy is `unless-stopped`: an app that crashes from memory exhaustion comes back on its own, which is the
  kind of self-healing the `idle` arm measures. Every scoring round counts an app that restarts itself during the
  measurement as a failure.

