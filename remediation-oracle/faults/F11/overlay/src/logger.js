const fs = require("fs");
const path = require("path");
const config = require("./config");

const LEVELS = { debug: 10, info: 20, warn: 30, error: 40 };
const threshold = LEVELS[config.logLevel] || LEVELS.info;
const LOG_FILE = path.join(config.logDir, "app.log");

fs.mkdirSync(config.logDir, { recursive: true });

function write(level, msg, fields = {}) {
  if (LEVELS[level] < threshold) return;
  const line = JSON.stringify({ ts: new Date().toISOString(), level, msg, ...fields }) + "\n";
  fs.appendFileSync(LOG_FILE, line);
  if (level !== "debug") process.stdout.write(line);
}

module.exports = {
  debug: (msg, fields) => write("debug", msg, fields),
  info: (msg, fields) => write("info", msg, fields),
  warn: (msg, fields) => write("warn", msg, fields),
  error: (msg, fields) => write("error", msg, fields),
};

