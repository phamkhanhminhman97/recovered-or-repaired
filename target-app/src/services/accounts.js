const { pool } = require("../db");

async function deposit({ depositId, accountId, amount }) {
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    const inserted = await client.query(
      "INSERT INTO deposits (id, account_id, amount) VALUES ($1, $2, $3) ON CONFLICT (id) DO NOTHING",
      [depositId, accountId, amount]
    );
    if (inserted.rowCount === 1) {
      await client.query("UPDATE accounts SET balance = balance + $1 WHERE id = $2", [amount, accountId]);
    }
    await client.query("COMMIT");
  } catch (err) {
    await client.query("ROLLBACK");
    throw err;
  } finally {
    client.release();
  }
}

module.exports = { deposit };
