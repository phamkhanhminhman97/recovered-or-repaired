CREATE TABLE IF NOT EXISTS accounts (
  id INT PRIMARY KEY,
  balance BIGINT NOT NULL DEFAULT 0
);
INSERT INTO accounts (id, balance) VALUES (1, 0), (2, 0), (3, 0) ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS deposits (
  id TEXT PRIMARY KEY,
  account_id INT NOT NULL REFERENCES accounts(id),
  amount BIGINT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS transfers (
  id TEXT PRIMARY KEY,
  from_id INT NOT NULL REFERENCES accounts(id),
  to_id INT NOT NULL REFERENCES accounts(id),
  amount BIGINT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS orders (
  id TEXT PRIMARY KEY,
  account_id INT NOT NULL REFERENCES accounts(id),
  sku TEXT NOT NULL,
  quantity INT NOT NULL,
  amount_cents BIGINT NOT NULL,
  currency TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS items (
  id SERIAL PRIMARY KEY,
  value INT NOT NULL,
  name TEXT NOT NULL
);
INSERT INTO items (value, name)
SELECT (random() * 100000)::int, 'item-' || g FROM generate_series(1, 1000000) AS g;
