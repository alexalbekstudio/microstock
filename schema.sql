-- schema.sql (PostgreSQL verzija - 2026-10-04)
-- ============================================
-- DROP VIEW-ova pre CREATE (da bi se osvežili tipovi kolona)
-- ============================================
DROP VIEW IF EXISTS v_order_profit;
DROP VIEW IF EXISTS v_project_summary;
-- Tabele
CREATE TABLE IF NOT EXISTS channels (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    fee_percent NUMERIC(6,2) DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS products (
    id           SERIAL PRIMARY KEY,
    user_id      INTEGER REFERENCES users(id) ON DELETE CASCADE,
    sku          TEXT UNIQUE NOT NULL,
    name         TEXT NOT NULL,
    price        NUMERIC(12,2) NOT NULL DEFAULT 0,
    cost         NUMERIC(12,2) NOT NULL DEFAULT 0,
    stock        INTEGER NOT NULL DEFAULT 0,
    low_stock_at INTEGER NOT NULL DEFAULT 3,
    active       INTEGER NOT NULL DEFAULT 1,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_products_name ON products(name);
CREATE INDEX IF NOT EXISTS idx_products_sku  ON products(sku);

CREATE TABLE IF NOT EXISTS orders (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER REFERENCES users(id) ON DELETE CASCADE,
    external_id     TEXT,
    source          TEXT DEFAULT 'manual',
    customer_name   TEXT NOT NULL,
    channel_id      INTEGER NOT NULL REFERENCES channels(id),
    status          TEXT NOT NULL DEFAULT 'new',
    note            TEXT,
    shipping_cost   NUMERIC(12,2) DEFAULT 0,
    shipping_method TEXT DEFAULT '',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_orders_status  ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_channel ON orders(channel_id);
CREATE INDEX IF NOT EXISTS idx_orders_ext     ON orders(external_id);

CREATE TABLE IF NOT EXISTS order_items (
    id         SERIAL PRIMARY KEY,
    order_id   INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    qty        INTEGER NOT NULL CHECK (qty > 0),
    unit_price NUMERIC(12,2) NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_log (
    id          SERIAL PRIMARY KEY,
    source      TEXT NOT NULL,
    external_id TEXT,
    order_id    INTEGER,
    payload     TEXT,
    status      TEXT,
    message     TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO channels (name, fee_percent) VALUES
    ('Instagram', 0.0),
    ('WhatsApp',  0.0),
    ('Etsy',      6.5),
    ('Faire',     15.0),
    ('Lično',     0.0)
ON CONFLICT (name) DO NOTHING;

-- VIEW za profit (identična logika, samo PostgreSQL sintaksa)
CREATE OR REPLACE VIEW v_order_profit AS
SELECT
    o.id                AS order_id,
    o.user_id           AS user_id,          -- ← DODATO
    o.created_at::timestamp AS order_date,
    o.status            AS status,
    c.id                AS channel_id,
    c.name              AS channel_name,
    c.fee_percent       AS fee_percent,
    p.id                AS product_id,
    p.sku               AS sku,
    p.name              AS product_name,
    p.cost              AS unit_cost,
    oi.qty              AS qty,
    oi.unit_price       AS unit_price,
    (oi.qty * oi.unit_price)                                 AS revenue,
    (oi.qty * oi.unit_price * c.fee_percent / 100.0)         AS channel_fee,
    (oi.qty * p.cost)                                        AS product_cost,
    COALESCE(o.shipping_cost, 0) *
      (oi.qty * oi.unit_price) /
      NULLIF((SELECT SUM(oi2.qty * oi2.unit_price)
              FROM order_items oi2
              WHERE oi2.order_id = o.id), 0)                 AS shipping_cost,
    (oi.qty * oi.unit_price)
      - (oi.qty * oi.unit_price * c.fee_percent / 100.0)
      - (oi.qty * p.cost)
      - COALESCE(o.shipping_cost, 0) *
        (oi.qty * oi.unit_price) /
        NULLIF((SELECT SUM(oi2.qty * oi2.unit_price)
                FROM order_items oi2
                WHERE oi2.order_id = o.id), 0)               AS profit
FROM order_items oi
JOIN orders   o ON o.id = oi.order_id
JOIN products p ON p.id = oi.product_id
JOIN channels c ON c.id = o.channel_id
WHERE o.status != 'cancelled';

-- Ostale tabele (team_members, projects, time_entries, project_expenses, users, import_logs, exchange_rates) — ista logika:
CREATE TABLE IF NOT EXISTS team_members (
    id            SERIAL PRIMARY KEY,
    name          TEXT NOT NULL,
    role          TEXT,
    hourly_rate   NUMERIC(12,2) NOT NULL DEFAULT 0,
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS projects (
    id                  SERIAL PRIMARY KEY,
    user_id             INTEGER REFERENCES users(id) ON DELETE CASCADE,
    code                TEXT,
    name                TEXT NOT NULL,
    client              TEXT,
    contract_value      NUMERIC(12,2) DEFAULT 0,
    start_date          DATE,
    deadline            DATE,
    status              TEXT DEFAULT 'active',
    notes               TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_alert_level    TEXT DEFAULT NULL,
    last_alert_sent_at  TIMESTAMP DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);

CREATE TABLE IF NOT EXISTS time_entries (
    id           SERIAL PRIMARY KEY,
    project_id   INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    member_id    INTEGER NOT NULL REFERENCES team_members(id),
    entry_date   DATE NOT NULL,
    hours        NUMERIC(8,2) NOT NULL CHECK (hours > 0),
    description  TEXT,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_time_project ON time_entries(project_id);

CREATE TABLE IF NOT EXISTS project_expenses (
    id           SERIAL PRIMARY KEY,
    project_id   INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    expense_date DATE NOT NULL,
    category     TEXT,
    description  TEXT,
    amount       NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_expense_project ON project_expenses(project_id);

CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    name          TEXT,
    role          TEXT NOT NULL DEFAULT 'admin',
    active        INTEGER NOT NULL DEFAULT 1,
    language      TEXT DEFAULT 'sr',
    currency      TEXT DEFAULT 'RSD',
    capital       NUMERIC(12,2) NOT NULL DEFAULT 0,   -- ← DODATO
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login    TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

CREATE OR REPLACE VIEW v_project_summary AS
SELECT
    p.id                                    AS project_id,
    p.user_id                               AS user_id,
    p.code                                  AS code,
    p.name                                  AS name,
    p.client                                AS client,
    p.status                                AS status,
    p.contract_value                        AS contract_value,
    p.start_date                            AS start_date,
    p.deadline                              AS deadline,
    p.last_alert_level,
    p.last_alert_sent_at,
    COALESCE((SELECT SUM(hours) FROM time_entries WHERE project_id = p.id), 0) AS total_hours,
    COALESCE((
        SELECT SUM(te.hours * tm.hourly_rate)
        FROM time_entries te JOIN team_members tm ON tm.id = te.member_id
        WHERE te.project_id = p.id
    ), 0) AS labor_cost,
    COALESCE((SELECT SUM(amount) FROM project_expenses WHERE project_id = p.id), 0) AS expense_cost
FROM projects p;

CREATE TABLE IF NOT EXISTS import_logs (
    id            SERIAL PRIMARY KEY,
    user_id       INTEGER,
    source        TEXT,
    filename      TEXT,
    rows_total    INTEGER DEFAULT 0,
    rows_imported INTEGER DEFAULT 0,
    rows_skipped  INTEGER DEFAULT 0,
    rows_failed   INTEGER DEFAULT 0,
    errors        TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS exchange_rates (
    id              SERIAL PRIMARY KEY,
    source_currency TEXT NOT NULL,
    target_currency TEXT NOT NULL,
    rate            NUMERIC(12,6) NOT NULL,
    rate_date       DATE NOT NULL,
    fetched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_currency, target_currency, rate_date)
);

-- ============================================
-- PRICING (Alat #4 — Kalkulator cena)
-- ============================================

CREATE TABLE IF NOT EXISTS pricing_history (
    id            SERIAL PRIMARY KEY,
    user_id       INTEGER REFERENCES users(id),
    product_id    INTEGER REFERENCES products(id) ON DELETE SET NULL,
    product_name  TEXT,
    mode          TEXT,
    cost          NUMERIC(12,2) DEFAULT 0,
    shipping      NUMERIC(12,2) DEFAULT 0,
    fee_pct       NUMERIC(6,2)  DEFAULT 0,
    tax_pct       NUMERIC(6,2)  DEFAULT 0,
    margin_pct    NUMERIC(6,2)  DEFAULT 0,
    price         NUMERIC(12,2) DEFAULT 0,
    profit        NUMERIC(12,2) DEFAULT 0,
    markup_pct    NUMERIC(8,2)  DEFAULT 0,
    applied       INTEGER DEFAULT 0,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pricing_history_user ON pricing_history(user_id);
CREATE INDEX IF NOT EXISTS idx_pricing_history_prod ON pricing_history(product_id);


CREATE TABLE IF NOT EXISTS channel_presets (
    id         SERIAL PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    fee_pct    NUMERIC(6,2) NOT NULL DEFAULT 0,
    tax_pct    NUMERIC(6,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- CAPITAL (Alat #5 — Praćenje kapitala)
-- ============================================
CREATE TABLE IF NOT EXISTS capital_transactions (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    type        TEXT NOT NULL,
    amount      NUMERIC(12,2) NOT NULL,
    balance     NUMERIC(12,2) NOT NULL,
    note        TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_capital_tx_user
ON capital_transactions(user_id, created_at DESC);

INSERT INTO channels (name, fee_percent) VALUES
    ('Instagram', 0.0),
    ('WhatsApp',  0.0),
    ('Etsy',      6.5),
    ('Faire',     15.0),
    ('Lično',     0.0),
    ('Shopify',   0.0),    -- ← DODATO
    ('Gumroad',   0.0),    -- ← DODATO
    ('Payhip',    0.0),    -- ← DODATO
    ('TikTok',    0.0)     -- ← DODATO
ON CONFLICT (name) DO NOTHING;

-- ============================================
-- ADMIN TRACKING TABELE
-- ============================================

-- 1. Beleži svaki login i posetu stranici
CREATE TABLE IF NOT EXISTS user_activity (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    endpoint        VARCHAR(120),           -- npr. 'login', 'inventory.list'
    method          VARCHAR(10),            -- GET, POST
    path            VARCHAR(255),           -- /inventory/orders
    response_code   INTEGER,                -- 200, 302, 404...
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_activity_user    ON user_activity(user_id);
CREATE INDEX IF NOT EXISTS idx_user_activity_created ON user_activity(created_at);
CREATE INDEX IF NOT EXISTS idx_user_activity_endpoint ON user_activity(endpoint);

-- 2. Pretplate po korisniku
CREATE TABLE IF NOT EXISTS subscriptions (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan_name       VARCHAR(20) NOT NULL,   -- starter, pro, business, enterprise
    status          VARCHAR(20) NOT NULL DEFAULT 'active',  -- active, expired, canceled, trial
    start_date      DATE NOT NULL DEFAULT CURRENT_DATE,
    end_date        DATE,
    renewal_date    DATE,
    is_self_hosted  BOOLEAN NOT NULL DEFAULT FALSE,
    license_key     VARCHAR(120),           -- za Enterprise
    sla_level       VARCHAR(20),            -- '12h', '24h', '48h'
    notes           TEXT,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_user   ON subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status);
CREATE INDEX IF NOT EXISTS idx_subscriptions_plan   ON subscriptions(plan_name);

-- 3. Koliko puta je koja funkcija iskorišćena (po mesecu)
CREATE TABLE IF NOT EXISTS usage_logs (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    feature_code    VARCHAR(60) NOT NULL,   -- npr. 'create_order', 'add_product'
    period          VARCHAR(7) NOT NULL,    -- '2026-10'
    count           INTEGER NOT NULL DEFAULT 0,
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, feature_code, period)
);

CREATE INDEX IF NOT EXISTS idx_usage_logs_user    ON usage_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_usage_logs_period  ON usage_logs(period);
CREATE INDEX IF NOT EXISTS idx_usage_logs_feature ON usage_logs(feature_code);