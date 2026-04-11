SET search_path TO public;

CREATE TABLE regions (
    region_id INTEGER PRIMARY KEY,
    region_name TEXT NOT NULL UNIQUE
);

CREATE TABLE customer_segments (
    segment_id INTEGER PRIMARY KEY,
    segment_name TEXT NOT NULL UNIQUE
);

CREATE TABLE stores (
    store_id INTEGER PRIMARY KEY,
    region_id INTEGER NOT NULL REFERENCES regions(region_id),
    store_name TEXT NOT NULL UNIQUE,
    opened_on DATE NOT NULL
);

CREATE TABLE sales_reps (
    sales_rep_id INTEGER PRIMARY KEY,
    store_id INTEGER NOT NULL REFERENCES stores(store_id),
    full_name TEXT NOT NULL,
    hire_date DATE NOT NULL
);

CREATE TABLE categories (
    category_id INTEGER PRIMARY KEY,
    category_name TEXT NOT NULL UNIQUE
);

CREATE TABLE brands (
    brand_id INTEGER PRIMARY KEY,
    brand_name TEXT NOT NULL UNIQUE
);

CREATE TABLE suppliers (
    supplier_id INTEGER PRIMARY KEY,
    supplier_name TEXT NOT NULL UNIQUE,
    supplier_tier TEXT NOT NULL,
    region_id INTEGER NOT NULL REFERENCES regions(region_id)
);

CREATE TABLE products (
    product_id INTEGER PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    category_id INTEGER NOT NULL REFERENCES categories(category_id),
    brand_id INTEGER NOT NULL REFERENCES brands(brand_id),
    list_price NUMERIC(10, 2) NOT NULL,
    release_date DATE NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE product_suppliers (
    product_id INTEGER NOT NULL REFERENCES products(product_id),
    supplier_id INTEGER NOT NULL REFERENCES suppliers(supplier_id),
    unit_cost NUMERIC(10, 2) NOT NULL,
    lead_time_days INTEGER NOT NULL,
    preferred_supplier BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (product_id, supplier_id)
);

CREATE TABLE promotions (
    promotion_id INTEGER PRIMARY KEY,
    promotion_name TEXT NOT NULL UNIQUE,
    discount_pct NUMERIC(5, 2) NOT NULL,
    channel TEXT NOT NULL,
    starts_on DATE NOT NULL,
    ends_on DATE NOT NULL
);

CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    segment_id INTEGER NOT NULL REFERENCES customer_segments(segment_id),
    region_id INTEGER NOT NULL REFERENCES regions(region_id),
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    joined_on DATE NOT NULL,
    lifetime_value NUMERIC(12, 2) NOT NULL DEFAULT 0
);

CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    store_id INTEGER NOT NULL REFERENCES stores(store_id),
    sales_rep_id INTEGER NOT NULL REFERENCES sales_reps(sales_rep_id),
    promotion_id INTEGER REFERENCES promotions(promotion_id),
    ordered_at TIMESTAMPTZ NOT NULL,
    order_status TEXT NOT NULL,
    order_channel TEXT NOT NULL
);

CREATE TABLE order_items (
    order_item_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(order_id),
    product_id INTEGER NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(10, 2) NOT NULL,
    discount_amount NUMERIC(10, 2) NOT NULL DEFAULT 0
);

CREATE TABLE payments (
    payment_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL UNIQUE REFERENCES orders(order_id),
    payment_method TEXT NOT NULL,
    paid_at TIMESTAMPTZ NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    fee_amount NUMERIC(10, 2) NOT NULL DEFAULT 0
);

CREATE TABLE shipments (
    shipment_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL UNIQUE REFERENCES orders(order_id),
    warehouse_region_id INTEGER NOT NULL REFERENCES regions(region_id),
    carrier TEXT NOT NULL,
    shipped_at TIMESTAMPTZ NOT NULL,
    delivered_at TIMESTAMPTZ,
    shipping_cost NUMERIC(10, 2) NOT NULL,
    shipment_status TEXT NOT NULL
);

CREATE TABLE return_requests (
    return_id INTEGER PRIMARY KEY,
    order_item_id INTEGER NOT NULL UNIQUE REFERENCES order_items(order_item_id),
    requested_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ,
    return_reason TEXT NOT NULL,
    return_status TEXT NOT NULL,
    refund_amount NUMERIC(10, 2) NOT NULL
);

CREATE TABLE support_tickets (
    ticket_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    order_id INTEGER REFERENCES orders(order_id),
    opened_at TIMESTAMPTZ NOT NULL,
    closed_at TIMESTAMPTZ,
    ticket_type TEXT NOT NULL,
    priority TEXT NOT NULL,
    satisfaction_score INTEGER
);

CREATE TABLE inventory_snapshots (
    snapshot_id INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(product_id),
    store_id INTEGER NOT NULL REFERENCES stores(store_id),
    snapshot_date DATE NOT NULL,
    units_on_hand INTEGER NOT NULL
);

INSERT INTO regions (region_id, region_name) VALUES
    (1, 'North America'),
    (2, 'Europe'),
    (3, 'Latin America'),
    (4, 'Asia Pacific');

INSERT INTO customer_segments (segment_id, segment_name) VALUES
    (1, 'Enterprise'),
    (2, 'SMB'),
    (3, 'Consumer'),
    (4, 'Loyalty');

INSERT INTO stores (store_id, region_id, store_name, opened_on) VALUES
    (1, 1, 'Seattle Hub', DATE '2021-01-10'),
    (2, 1, 'Austin Hub', DATE '2021-03-18'),
    (3, 2, 'Berlin Hub', DATE '2021-05-22'),
    (4, 2, 'Madrid Hub', DATE '2021-07-14'),
    (5, 3, 'Bogota Hub', DATE '2021-09-05'),
    (6, 3, 'Santiago Hub', DATE '2021-11-11'),
    (7, 4, 'Singapore Hub', DATE '2022-02-07'),
    (8, 4, 'Sydney Hub', DATE '2022-04-19');

INSERT INTO sales_reps (sales_rep_id, store_id, full_name, hire_date)
SELECT
    rep_id,
    ((rep_id - 1) / 2) + 1,
    'Sales Rep ' || rep_id,
    DATE '2021-01-01' + ((rep_id - 1) * 19)
FROM generate_series(1, 16) AS rep_id;

INSERT INTO categories (category_id, category_name) VALUES
    (1, 'Electronics'),
    (2, 'Home Office'),
    (3, 'Fitness'),
    (4, 'Travel'),
    (5, 'Kitchen'),
    (6, 'Gaming');

INSERT INTO brands (brand_id, brand_name) VALUES
    (1, 'Northwind'),
    (2, 'Orbit'),
    (3, 'Summit'),
    (4, 'BluePeak'),
    (5, 'Aurora');

INSERT INTO suppliers (supplier_id, supplier_name, supplier_tier, region_id) VALUES
    (1, 'Atlas Supply', 'gold', 1),
    (2, 'Crest Components', 'silver', 1),
    (3, 'Helios Imports', 'gold', 2),
    (4, 'Silverline Goods', 'bronze', 2),
    (5, 'Pacific Trade', 'gold', 4),
    (6, 'Andes Wholesale', 'silver', 3),
    (7, 'Nova Procurement', 'silver', 4),
    (8, 'Harbor Direct', 'bronze', 3);

INSERT INTO products (
    product_id,
    sku,
    product_name,
    category_id,
    brand_id,
    list_price,
    release_date,
    active
)
SELECT
    product_id,
    'SKU-' || LPAD(product_id::TEXT, 4, '0'),
    'Product ' || product_id,
    ((product_id - 1) % 6) + 1,
    ((product_id - 1) % 5) + 1,
    ROUND((25 + product_id * 2.7 + ((product_id % 4) * 6))::NUMERIC, 2),
    DATE '2022-01-01' + (product_id * 9),
    TRUE
FROM generate_series(1, 48) AS product_id;

INSERT INTO product_suppliers (
    product_id,
    supplier_id,
    unit_cost,
    lead_time_days,
    preferred_supplier
)
SELECT
    product_id,
    ((product_id + supplier_offset - 1) % 8) + 1,
    ROUND((p.list_price * (0.42 + supplier_offset * 0.05))::NUMERIC, 2),
    5 + ((product_id + supplier_offset * 3) % 12),
    supplier_offset = 1
FROM products AS p
CROSS JOIN generate_series(1, 2) AS supplier_offset;

INSERT INTO promotions (
    promotion_id,
    promotion_name,
    discount_pct,
    channel,
    starts_on,
    ends_on
) VALUES
    (1, 'Winter Push', 8.00, 'online', DATE '2023-01-05', DATE '2023-02-28'),
    (2, 'Spring Bundle', 10.00, 'all', DATE '2023-03-10', DATE '2023-05-31'),
    (3, 'Midyear Upgrade', 6.50, 'store', DATE '2023-06-01', DATE '2023-07-15'),
    (4, 'Holiday Preview', 12.00, 'online', DATE '2023-10-20', DATE '2023-12-05'),
    (5, 'Retention Offer', 7.50, 'all', DATE '2024-02-01', DATE '2024-03-15'),
    (6, 'Year End Close', 9.00, 'wholesale', DATE '2024-11-01', DATE '2024-12-20');

INSERT INTO customers (
    customer_id,
    segment_id,
    region_id,
    full_name,
    email,
    joined_on,
    lifetime_value
)
SELECT
    customer_id,
    ((customer_id - 1) % 4) + 1,
    ((customer_id - 1) % 4) + 1,
    'Customer ' || customer_id,
    'customer' || customer_id || '@example.com',
    DATE '2022-01-01' + ((customer_id * 11) % 540),
    ROUND((350 + customer_id * 41 + ((customer_id % 7) * 55))::NUMERIC, 2)
FROM generate_series(1, 220) AS customer_id;

INSERT INTO orders (
    order_id,
    customer_id,
    store_id,
    sales_rep_id,
    promotion_id,
    ordered_at,
    order_status,
    order_channel
)
SELECT
    order_id,
    ((order_id * 7 - 1) % 220) + 1,
    ((order_id - 1) % 8) + 1,
    ((((order_id - 1) % 8) * 2) + ((order_id % 2) + 1)),
    CASE
        WHEN order_id % 5 = 0 THEN ((order_id - 1) % 6) + 1
        ELSE NULL
    END,
    TIMESTAMPTZ '2023-01-01 09:00:00+00' + (((order_id * 17) % 730) || ' days')::INTERVAL
        + (((order_id * 3) % 10) || ' hours')::INTERVAL,
    CASE
        WHEN order_id % 17 = 0 THEN 'cancelled'
        WHEN order_id % 5 = 0 THEN 'processing'
        WHEN order_id % 3 = 0 THEN 'shipped'
        ELSE 'delivered'
    END,
    CASE
        WHEN order_id % 6 = 0 THEN 'wholesale'
        WHEN order_id % 2 = 0 THEN 'online'
        ELSE 'store'
    END
FROM generate_series(1, 900) AS order_id;

INSERT INTO order_items (
    order_item_id,
    order_id,
    product_id,
    quantity,
    unit_price,
    discount_amount
)
SELECT
    ((o.order_id - 1) * 3) + line_no,
    o.order_id,
    ((o.order_id * 5 + line_no * 7 - 1) % 48) + 1,
    1 + ((o.order_id + line_no) % 4),
    ROUND((p.list_price * (1 + (((o.order_id + line_no) % 5) * 0.025)))::NUMERIC, 2),
    ROUND(
        (
            p.list_price
            * (1 + (((o.order_id + line_no) % 5) * 0.025))
            * (1 + ((o.order_id + line_no) % 4))
            * COALESCE(pr.discount_pct, 0)
            / 100.0
        )::NUMERIC,
        2
    )
FROM orders AS o
JOIN generate_series(1, 1 + (o.order_id % 3)) AS line_no ON TRUE
JOIN products AS p
    ON p.product_id = ((o.order_id * 5 + line_no * 7 - 1) % 48) + 1
LEFT JOIN promotions AS pr
    ON pr.promotion_id = o.promotion_id;

INSERT INTO payments (
    payment_id,
    order_id,
    payment_method,
    paid_at,
    amount,
    fee_amount
)
SELECT
    o.order_id,
    o.order_id,
    CASE
        WHEN o.order_id % 4 = 0 THEN 'wire'
        WHEN o.order_id % 3 = 0 THEN 'paypal'
        WHEN o.order_id % 2 = 0 THEN 'card'
        ELSE 'invoice'
    END,
    o.ordered_at + INTERVAL '1 day',
    ROUND(SUM((oi.quantity * oi.unit_price) - oi.discount_amount)::NUMERIC, 2),
    ROUND((SUM((oi.quantity * oi.unit_price) - oi.discount_amount) * 0.021)::NUMERIC, 2)
FROM orders AS o
JOIN order_items AS oi
    ON oi.order_id = o.order_id
WHERE o.order_status <> 'cancelled'
GROUP BY o.order_id, o.ordered_at;

INSERT INTO shipments (
    shipment_id,
    order_id,
    warehouse_region_id,
    carrier,
    shipped_at,
    delivered_at,
    shipping_cost,
    shipment_status
)
SELECT
    o.order_id,
    o.order_id,
    s.region_id,
    CASE
        WHEN o.order_id % 3 = 0 THEN 'DHL'
        WHEN o.order_id % 2 = 0 THEN 'FedEx'
        ELSE 'UPS'
    END,
    o.ordered_at + INTERVAL '2 days',
    CASE
        WHEN o.order_status = 'delivered' THEN o.ordered_at + INTERVAL '6 days'
        ELSE NULL
    END,
    ROUND((8 + (o.order_id % 6) * 1.9)::NUMERIC, 2),
    CASE
        WHEN o.order_status = 'delivered' THEN 'delivered'
        ELSE 'in_transit'
    END
FROM orders AS o
JOIN stores AS s
    ON s.store_id = o.store_id
WHERE o.order_status IN ('shipped', 'delivered');

INSERT INTO return_requests (
    return_id,
    order_item_id,
    requested_at,
    resolved_at,
    return_reason,
    return_status,
    refund_amount
)
SELECT
    oi.order_item_id,
    oi.order_item_id,
    o.ordered_at + INTERVAL '14 days',
    o.ordered_at + INTERVAL '19 days',
    CASE
        WHEN oi.order_item_id % 3 = 0 THEN 'damaged'
        WHEN oi.order_item_id % 3 = 1 THEN 'late_delivery'
        ELSE 'changed_mind'
    END,
    'approved',
    ROUND((((oi.quantity * oi.unit_price) - oi.discount_amount) * 0.85)::NUMERIC, 2)
FROM order_items AS oi
JOIN orders AS o
    ON o.order_id = oi.order_id
WHERE o.order_status = 'delivered'
  AND oi.order_item_id % 11 = 0;

INSERT INTO support_tickets (
    ticket_id,
    customer_id,
    order_id,
    opened_at,
    closed_at,
    ticket_type,
    priority,
    satisfaction_score
)
SELECT
    o.order_id,
    o.customer_id,
    o.order_id,
    o.ordered_at + INTERVAL '3 days',
    o.ordered_at + INTERVAL '5 days',
    CASE
        WHEN o.order_id % 3 = 0 THEN 'delivery'
        WHEN o.order_id % 3 = 1 THEN 'billing'
        ELSE 'product'
    END,
    CASE
        WHEN o.order_id % 5 = 0 THEN 'high'
        WHEN o.order_id % 2 = 0 THEN 'medium'
        ELSE 'low'
    END,
    3 + (o.order_id % 3)
FROM orders AS o
WHERE o.order_id % 14 = 0
  AND o.order_status <> 'cancelled';

INSERT INTO inventory_snapshots (
    snapshot_id,
    product_id,
    store_id,
    snapshot_date,
    units_on_hand
)
SELECT
    ((month_idx - 1) * 384) + ((product_id - 1) * 8) + store_id,
    product_id,
    store_id,
    DATE '2025-01-01' + ((month_idx - 1) * INTERVAL '1 month'),
    20 + ((product_id * 3 + store_id * 7 + month_idx * 5) % 95)
FROM generate_series(1, 6) AS month_idx
CROSS JOIN generate_series(1, 48) AS product_id
CROSS JOIN generate_series(1, 8) AS store_id;

ANALYZE;
