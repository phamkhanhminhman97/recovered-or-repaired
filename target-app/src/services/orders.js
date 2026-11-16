const { pool } = require("../db");
const catalog = require("./catalog");
const pricing = require("./pricing");
const currency = require("./currency");
const payments = require("./payments");

async function placeOrder({ orderId, accountId, sku, quantity = 1, currency: cur = "USD" }) {
  if (catalog.listPrice(sku) === undefined) {
    throw new Error("unknown sku " + sku);
  }
  const unitPrice = await pricing.priceFor(sku);
  const amountCents = currency.toUsdCents(unitPrice * quantity, cur);

  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    await client.query(
      "INSERT INTO orders (id, account_id, sku, quantity, amount_cents, currency, status) VALUES ($1, $2, $3, $4, $5, $6, 'pending') ON CONFLICT (id) DO NOTHING",
      [orderId, accountId, sku, quantity, amountCents, cur]
    );
    await payments.charge(orderId, amountCents);
    await client.query("UPDATE orders SET status = 'paid' WHERE id = $1", [orderId]);
    await client.query("COMMIT");
  } catch (err) {
    await client.query("ROLLBACK");
    throw err;
  } finally {
    client.release();
  }
}

module.exports = { placeOrder };
