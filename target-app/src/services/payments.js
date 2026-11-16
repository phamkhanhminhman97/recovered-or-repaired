const config = require("../config");
const partner = require("../partner");

async function charge(orderId, amountCents) {
  return partner.request("/v1/charges", {
    method: "POST",
    body: { orderId, amountCents },
    headers: { authorization: "Bearer " + config.paymentApiKey },
  });
}

module.exports = { charge };
