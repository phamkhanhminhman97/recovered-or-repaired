const config = require("../config");
const partner = require("../partner");
const catalog = require("./catalog");
const logger = require("../logger");

async function priceFor(sku) {
  try {
    const data = await partner.request(`/v1/prices/${encodeURIComponent(sku)}`, {
      timeoutMs: config.downstreamTimeoutMs,
    });
    return data.priceCents;
  } catch (err) {
    logger.warn("pricing unavailable, using list price", { sku, reason: err.name === "AbortError" ? "timeout" : err.message });
    return catalog.listPrice(sku);
  }
}

module.exports = { priceFor };
