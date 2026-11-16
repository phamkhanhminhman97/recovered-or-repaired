const { pool } = require("../db");

const LIMIT_PER_DEPOSIT = 1000000;

async function checkLimits(accountId, amount) {
  // Limits are evaluated asynchronously (anti-fraud rules).
  await new Promise((r) => setTimeout(r, 5));
  if (amount > LIMIT_PER_DEPOSIT) throw new Error("deposit over limit");
}

async function deposit({ depositId, accountId, amount }) {
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    const inserted = await client.query(
      "INSERT INTO deposits (id, account_id, amount) VALUES ($1, $2, $3) ON CONFLICT (id) DO NOTHING",
      [depositId, accountId, amount]
    );
    if (inserted.rowCount === 1) {
      const { rows } = await pool.query("SELECT balance FROM accounts WHERE id = $1", [accountId]);
      await checkLimits(accountId, amount);
      const newBalance = Number(rows[0].balance) + amount;
      await client.query("UPDATE accounts SET balance = $1 WHERE id = $2", [newBalance, accountId]);
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

