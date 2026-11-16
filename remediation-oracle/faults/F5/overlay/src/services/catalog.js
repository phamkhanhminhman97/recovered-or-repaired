const { pool } = require("../db");

// List prices in USD cents, used when the pricing partner is slow or unavailable.
const LIST_PRICES = {};
for (let i = 1; i <= 50; i += 1) LIST_PRICES[`SKU-${i}`] = 500 + i * 25;

function listPrice(sku) {
  return LIST_PRICES[sku];
}

async function getItems(ids) {
  const items = [];
  for (const id of ids) {
    const { rows } = await pool.query("SELECT id, value, name FROM items WHERE id = $1", [id]);
    if (rows[0]) items.push(rows[0]);
  }
  return items;
}

async function searchByValue(value) {
  const { rows } = await pool.query("SELECT id, name FROM items WHERE value = $1 LIMIT 50", [value]);
  return rows;
}

module.exports = { listPrice, getItems, searchByValue };

