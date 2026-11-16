const config = require("./config");

class PartnerError extends Error {
  constructor(status, body) {
    super("partner api responded " + status);
    this.status = status;
    this.body = body;
  }
}

async function request(pathname, { method = "GET", body, timeoutMs = 5000, headers = {} } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(config.partnerApiUrl + pathname, {
      method,
      headers: { "content-type": "application/json", ...headers },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
    const text = await res.text();
    const data = text ? JSON.parse(text) : {};
    if (!res.ok) {
      const err = new PartnerError(res.status, data);
      err.retryAfterSec = Number(res.headers.get("retry-after") || 0);
      throw err;
    }
    return data;
  } finally {
    clearTimeout(timer);
  }
}

module.exports = { request, PartnerError };
