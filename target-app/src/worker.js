const { Worker } = require("bullmq");
const { connection, deadLetters } = require("./queue");
const logger = require("./logger");
const metrics = require("./metrics");
const orders = require("./services/orders");
const accounts = require("./services/accounts");
const transfers = require("./services/transfers");
const notifications = require("./services/notifications");

const handlers = {
  order: (data) => orders.placeOrder(data),
  deposit: (data) => accounts.deposit(data),
  transfer: (data) => transfers.transfer(data),
  notification: (data) => notifications.send(data),
};

async function processJob(job) {
  const handler = handlers[job.name];
  if (!handler) throw new Error("no handler for job " + job.name);
  const started = Date.now();
  logger.info("processing job", { job: job.name, id: job.id, attempt: job.attemptsMade + 1, data: job.data });
  await handler(job.data);
  logger.info("job completed", { job: job.name, id: job.id, ms: Date.now() - started });
}

function start() {
  const worker = new Worker("jobs", processJob, { connection, concurrency: 5 });
  worker.on("completed", () => metrics.recordJob(true));
  worker.on("failed", async (job, err) => {
    metrics.recordJob(false);
    if (!job) return;
    try {
      const attempts = (job.opts && job.opts.attempts) || 1;
      logger.warn("job attempt failed", { job: job.name, id: job.id, attempt: job.attemptsMade, error: err.message });
      if (job.attemptsMade >= attempts) {
        await deadLetters.add(job.name, { ...job.data, error: err.message }, { jobId: job.id });
        logger.error("job moved to dead letter queue", { job: job.name, id: job.id, error: err.message });
      }
    } catch (e) {
      console.error("failed to record job failure:", e.message);
    }
  });
  return worker;
}

module.exports = { start };
