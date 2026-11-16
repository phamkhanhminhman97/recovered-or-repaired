const num = (v, d) => (v === undefined || v === "" ? d : Number(v));

module.exports = {
  port: num(process.env.PORT, 3000),
  databaseUrl: process.env.DATABASE_URL,
  redisUrl: process.env.REDIS_URL,
  dbTimeoutMs: num(process.env.DB_TIMEOUT_MS, 5000),
  poolMax: num(process.env.POOL_MAX, 10),
  partnerApiUrl: process.env.PARTNER_API_URL || "http://localhost:8080",
  paymentApiKey: process.env.PAYMENT_API_KEY || "",
  downstreamTimeoutMs: num(process.env.DOWNSTREAM_TIMEOUT_MS, 500),
  logDir: process.env.LOG_DIR || "./logs",
  logLevel: process.env.LOG_LEVEL || "info",
};
