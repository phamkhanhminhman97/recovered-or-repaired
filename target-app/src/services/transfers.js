const { pool } = require("../db");

async function transfer({ transferId, fromId, toId, amount }) {
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    // One lock per account pair, taken in a fixed order.
    const lo = Math.min(fromId, toId);
    const hi = Math.max(fromId, toId);
    await client.query("SELECT pg_advisory_xact_lock($1, $2)", [lo, hi]);
    const inserted = await client.query(
      "INSERT INTO transfers (id, from_id, to_id, amount) VALUES ($1, $2, $3, $4) ON CONFLICT (id) DO NOTHING",
      [transferId, fromId, toId, amount]
    );
    if (inserted.rowCount === 1) {
      await client.query("UPDATE accounts SET balance = balance - $1 WHERE id = $2", [amount, fromId]);
      await client.query("UPDATE accounts SET balance = balance + $1 WHERE id = $2", [amount, toId]);
    }
    await client.query("COMMIT");
  } catch (err) {
    await client.query("ROLLBACK");
    throw err;
  } finally {
    client.release();
  }
}

module.exports = { transfer };
