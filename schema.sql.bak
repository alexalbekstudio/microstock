-- schema.sql (kompletna nova verzija - 2026-10-03)

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS channels (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    fee_percent REAL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS products (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    sku          TEXT UNIQUE NOT NULL,
    name         TEXT NOT NULL,
    price        REAL NOT NULL DEFAULT 0,
    cost         REAL NOT NULL DEFAULT 0,
    stock        INTEGER NOT NULL DEFAULT 0,
    low_stock_at INTEGER NOT NULL DEFAULT 3,
    active       INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT DEFAULT (datetime('now')),
    updated_at   TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_products_name ON products(name);
CREATE INDEX IF NOT EXISTS idx_products_sku  ON products(sku);

CREATE TABLE IF NOT EXISTS orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id     TEXT,
    source          TEXT DEFAULT 'manual',
    customer_name   TEXT NOT NULL,
    channel_id      INTEGER NOT NULL,
    status          TEXT NOT NULL DEFAULT 'new',
    note            TEXT,
    -- NOVO: dostava
    shipping_cost   REAL DEFAULT 0,
    shipping_method TEXT DEFAULT '',
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (channel_id) REFERENCES channels(id)
);

CREATE INDEX IF NOT EXISTS idx_orders_status  ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_channel ON orders(channel_id);
CREATE INDEX IF NOT EXISTS idx_orders_ext     ON orders(external_id);

CREATE TABLE IF NOT EXISTS order_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id   INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    qty        INTEGER NOT NULL CHECK (qty > 0),
    unit_price REAL NOT NULL,
    FOREIGN KEY (order_id)   REFERENCES orders(id)   ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS sync_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL,
    external_id TEXT,
    order_id    INTEGER,
    payload     TEXT,
    status      TEXT,
    message     TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

INSERT OR IGNORE INTO channels (name, fee_percent) VALUES
    ('Instagram', 0.0),
    ('WhatsApp',  0.0),
    ('Etsy',      6.5),
    ('Faire',     15.0),
    ('Lično',     0.0);

-- ============================================
-- ALAT #2: Analitika - VIEW za profit (SA DOSTAVOM)
-- ============================================
-- VAŽNO: shipping_cost je trošak CELE narudžbine, ne po itemu.
-- Zato ga delimo srazmerno vrednosti itema u narudžbini.
-- Ako narudžbina ima 2 itema: 100 din i 300 din (ukupno 400),
-- shipping 40 din se deli: 10 din na prvi, 30 din na drugi.

CREATE VIEW IF NOT EXISTS v_order_profit AS
SELECT
    o.id                AS order_id,
    o.created_at        AS order_date,
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
    (oi.qty * oi.unit_price)                                    AS revenue,
    (oi.qty * oi.unit_price * c.fee_percent / 100.0)            AS channel_fee,
    (oi.qty * p.cost)                                           AS product_cost,
    -- Deo shipping_cost-a koji pripada ovom itemu:
    COALESCE(o.shipping_cost, 0) *
      (oi.qty * oi.unit_price) /
      NULLIF((SELECT SUM(oi2.qty * oi2.unit_price)
              FROM order_items oi2
              WHERE oi2.order_id = o.id), 0)                    AS shipping_cost,
    -- Profit = prihod - provizija - trošak proizvoda - dostava
    (oi.qty * oi.unit_price)
      - (oi.qty * oi.unit_price * c.fee_percent / 100.0)
      - (oi.qty * p.cost)
      - COALESCE(o.shipping_cost, 0) *
        (oi.qty * oi.unit_price) /
        NULLIF((SELECT SUM(oi2.qty * oi2.unit_price)
                FROM order_items oi2
                WHERE oi2.order_id = o.id), 0)                  AS profit
FROM order_items oi
JOIN orders   o ON o.id = oi.order_id
JOIN products p ON p.id = oi.product_id
JOIN channels c ON c.id = o.channel_id
WHERE o.status != 'cancelled';

-- ============================================
-- ALAT #3: Praćenje troškova projekata (USKLAĐENO SA BAZOM)
-- ============================================

CREATE TABLE IF NOT EXISTS team_members (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    role          TEXT,
    hourly_rate   REAL NOT NULL DEFAULT 0,
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS projects (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    code                TEXT,
    name                TEXT NOT NULL,
    client              TEXT,
    contract_value      REAL DEFAULT 0,
    start_date          TEXT,
    deadline            TEXT,
    status              TEXT DEFAULT 'active',
    notes               TEXT,
    created_at          TEXT DEFAULT (datetime('now')),
    updated_at          TEXT DEFAULT (datetime('now')),
    last_alert_level    TEXT DEFAULT NULL,
    last_alert_sent_at  TEXT DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);

CREATE TABLE IF NOT EXISTS time_entries (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id   INTEGER NOT NULL,
    member_id    INTEGER NOT NULL,
    entry_date   TEXT NOT NULL,
    hours        REAL NOT NULL CHECK (hours > 0),
    description  TEXT,
    created_at   TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (project_id) REFERENCES projects(id)     ON DELETE CASCADE,
    FOREIGN KEY (member_id)  REFERENCES team_members(id)
);

CREATE INDEX IF NOT EXISTS idx_time_project ON time_entries(project_id);

CREATE TABLE IF NOT EXISTS project_expenses (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id   INTEGER NOT NULL,
    expense_date TEXT NOT NULL,
    category     TEXT,
    description  TEXT,
    amount       REAL NOT NULL CHECK (amount >= 0),
    created_at   TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_expense_project ON project_expenses(project_id);

-- ============================================
-- AUTENTIFIKACIJA
-- ============================================

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    name          TEXT,
    role          TEXT NOT NULL DEFAULT 'admin',
    active        INTEGER NOT NULL DEFAULT 1,
    language      TEXT DEFAULT 'sr',
    currency      TEXT DEFAULT 'RSD',
    created_at    TEXT DEFAULT (datetime('now')),
    last_login    TEXT
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- ============================================
-- VIEW: Sažetak projekta
-- ============================================
CREATE VIEW IF NOT EXISTS v_project_summary AS
SELECT
    p.id                                    AS project_id,
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

-- ============================================
-- IMPORT LOGS (ispravljeno: INTEGER umesto SERIAL)
-- ============================================
CREATE TABLE IF NOT EXISTS import_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
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

-- ============================================
-- KURSEVI
-- ============================================
CREATE TABLE IF NOT EXISTS exchange_rates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_currency TEXT NOT NULL,
    target_currency TEXT NOT NULL,
    rate            REAL NOT NULL,
    rate_date       TEXT NOT NULL,
    fetched_at      TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_currency, target_currency, rate_date)
);