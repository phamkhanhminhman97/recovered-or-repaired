const { pool } = require("./db");
const { jobs, deadLetters } = require("./queue");

const counters = { httpRequests: 0, httpErrors: 0, jobsCompleted: 0, jobsFailed: 0 };
const latencies = [];

function recordHttp(ms, status) {
  counters.httpRequests += 1;
  if (status >= 500) counters.httpErrors += 1;
  latencies.push(ms);
  if (latencies.length > 500) latencies.shift();
}

function recordJob(ok) {
  if (ok) counters.jobsCompleted += 1;
  else counters.jobsFailed += 1;
}

async function snapshot() {
  const sorted = [...latencies].sort((a, b) => a - b);
  const p = (q) => (sorted.length ? sorted[Math.min(sorted.length - 1, Math.floor(q * sorted.length))] : 0);
  let queue = {};
  try {
    queue = await jobs.getJobCounts("waiting", "active", "delayed", "failed", "completed");
    queue.deadLetters = await deadLetters.count();
  } catch (err) {
    queue = { error: err.message };
  }
  return {
    ...counters,
    httpP50Ms: p(0.5),
    httpP99Ms: p(0.99),
    queue,
    dbPool: { total: pool.totalCount, idle: pool.idleCount, waiting: pool.waitingCount },
    memoryRssMb: Math.round(process.memoryUsage().rss / 1048576),
    uptimeSec: Math.round(process.uptime()),
  };
}

module.exports = { recordHttp, recordJob, snapshot };
