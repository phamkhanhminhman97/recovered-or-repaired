// Exchange rates to USD.
const RATES_TO_USD = {
  USD: 1,
  EUR: 1.08,
  GBP: 1.27,
  VND: 0.00004,
};

function toUsdCents(amountCents, currency) {
  const rate = RATES_TO_USD[currency];
  if (rate === undefined) throw new Error("unsupported currency " + currency);
  return Math.round(amountCents * rate);
}

module.exports = { toUsdCents };

