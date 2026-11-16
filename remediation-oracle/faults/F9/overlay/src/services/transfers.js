const { pool } = require("../db");

async function transfer({ transferId, fromId, toId, amount }) {
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    await client.query("SELECT balance FROM accounts WHERE id = $1 FOR UPDATE", [fromId]);
    await new Promise((r) => setTimeout(r, 20));
    await client.query("SELECT balance FROM accounts WHERE id = $1 FOR UPDATE", [toId]);
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

