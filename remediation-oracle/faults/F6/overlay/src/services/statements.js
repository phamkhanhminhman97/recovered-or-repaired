const { pool } = require("../db");

// Rendered statements are cached per account and requested date.
const cache = {};

function monthOf(asOf) {
  const d = asOf ? new Date(Number(asOf) || asOf) : new Date();
  return Number.isNaN(d.getTime()) ? new Date().toISOString().slice(0, 7) : d.toISOString().slice(0, 7);
}

function render(account, orders, month) {
  const lines = [];
  for (let i = 0; i < 2000; i += 1) {
    const o = orders[i % Math.max(1, orders.length)];
    lines.push(
      `<tr><td>${month}</td><td>${i}</td><td>${o ? o.sku : "-"}</td><td>${o ? o.amount_cents : 0}</td><td>${account.balance}</td></tr>`
    );
  }
  return `<table data-account="${account.id}">${lines.join("")}</table>`;
}

async function statementFor(accountId, asOf) {
  const month = monthOf(asOf);
  const key = `${accountId}:${asOf || month}`;
  if (cache[key]) return cache[key];
  const { rows: accounts } = await pool.query("SELECT id, balance FROM accounts WHERE id = $1", [accountId]);
  if (accounts.length === 0) return null;
  const { rows: orders } = await pool.query(
    "SELECT sku, amount_cents FROM orders WHERE account_id = $1 ORDER BY created_at DESC LIMIT 100",
    [accountId]
  );
  const html = render(accounts[0], orders, month);
  cache[key] = html;
  return html;
}

module.exports = { statementFor };

