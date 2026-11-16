const config = require("../config");
const partner = require("../partner");

async function send({ notificationId, userId, message }) {
  return partner.request("/v1/notifications", {
    method: "POST",
    body: { notificationId, userId, message },
    headers: { authorization: "Bearer " + config.paymentApiKey },
  });
}

module.exports = { send };

