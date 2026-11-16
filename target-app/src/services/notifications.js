const config = require("../config");
const partner = require("../partner");

const MAX_TRIES = 6;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function send({ notificationId, userId, message }) {
  for (let attempt = 1; ; attempt += 1) {
    try {
      return await partner.request("/v1/notifications", {
        method: "POST",
        body: { notificationId, userId, message },
        headers: { authorization: "Bearer " + config.paymentApiKey },
      });
    } catch (err) {
      if (err.status !== 429 || attempt >= MAX_TRIES) throw err;
      await sleep(Math.max(1, err.retryAfterSec) * 1000);
    }
  }
}

module.exports = { send };
