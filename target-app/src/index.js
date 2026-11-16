const crypto = require("crypto");
const express = require("express");
const config = require("./config");
const { pool, migrate } = require("./db");
const { enqueue } = require("./queue");
const logger = require("./logger");
const metrics = require("./metrics");
const worker = require("./worker");
const catalog = require("./services/catalog");
const statements = require("./services/statements");

const app = express();
app.use(express.json());
app.use((req, res, next) => {
  const started = Date.now();
  res.on("finish", () => metrics.recordHttp(Date.now() - started, res.statusCode));
  next();
});

const newId = (v) => (typeof v === "string" && v ? v : crypto.randomUUID());

function queued(name, build) {
  return async (req, res) => {
    try {
      const data = build(req.body || {});
      await enqueue(name, data, data.id);
      res.status(202).json({ id: data.id, status: "queued" });
    } catch (err) {
      logger.error("enqueue failed", { job: name, error: err.message });
      res.status(500).json({ error: err.message });
    }
  };
}

app.post("/orders", queued("order", (b) => {
  const orderId = newId(b.orderId);
  return { id: orderId, orderId, accountId: b.accountId || 1, sku: b.sku, quantity: b.quantity || 1, currency: b.currency || "USD" };
}));
app.post("/deposits", queued("deposit", (b) => {
  const depositId = newId(b.depositId);
  return { id: depositId, depositId, accountId: b.accountId || 1, amount: b.amount || 1 };
}));
app.post("/transfers", queued("transfer", (b) => {
  const transferId = newId(b.transferId);
  return { id: transferId, transferId, fromId: b.fromId, toId: b.toId, amount: b.amount || 1 };
}));
app.post("/notifications", queued("notification", (b) => {
  const notificationId = newId(b.notificationId);
  return { id: notificationId, notificationId, userId: b.userId || 1, message: b.message || "" };
}));

app.get("/accounts/:id/statement", async (req, res) => {
  try {
    const html = await statements.statementFor(Number(req.params.id), req.query.asOf);
    if (html === null) return res.status(404).json({ error: "account not found" });
    res.json({ accountId: Number(req.params.id), bytes: html.length });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.get("/catalog/items", async (req, res) => {
  try {
    const ids = String(req.query.ids || "").split(",").filter(Boolean).map(Number);
    res.json({ items: await catalog.getItems(ids) });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.get("/catalog/search", async (req, res) => {
  try {
    res.json({ items: await catalog.searchByValue(Number(req.query.value)) });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.get("/health", async (req, res) => {
  try {
    await pool.query("SELECT 1");
    res.json({ status: "ok" });
  } catch (err) {
    res.status(503).json({ status: "unhealthy", error: err.message });
  }
});

app.get("/metrics", async (req, res) => {
  res.json(await metrics.snapshot());
});

async function main() {
  await migrate();
  worker.start();
  app.listen(config.port, () => logger.info("order-service listening", { port: config.port }));
}

main().catch((err) => {
  logger.error("startup failed", { error: err.message });
  process.exit(1);
});
