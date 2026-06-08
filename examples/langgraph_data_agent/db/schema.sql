DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS shipments;
DROP TABLE IF EXISTS tracking_events;
DROP TABLE IF EXISTS carriers;
DROP TABLE IF EXISTS warehouses;
DROP TABLE IF EXISTS carrier_costs;
DROP TABLE IF EXISTS calendar;

CREATE TABLE orders (
    order_id TEXT PRIMARY KEY,
    order_date TEXT,
    country TEXT,
    promised_delivery_date TEXT,
    service TEXT,
    order_value REAL
);

CREATE TABLE shipments (
    shipment_id TEXT PRIMARY KEY,
    order_id TEXT,
    carrier TEXT,
    warehouse_id TEXT,
    ship_date TEXT,
    delivered_date TEXT,
    status TEXT,
    FOREIGN KEY(order_id) REFERENCES orders(order_id)
);

CREATE TABLE tracking_events (
    event_id TEXT PRIMARY KEY,
    shipment_id TEXT,
    event_time TEXT,
    event_type TEXT,
    location TEXT,
    FOREIGN KEY(shipment_id) REFERENCES shipments(shipment_id)
);

CREATE TABLE carriers (
    carrier TEXT PRIMARY KEY,
    carrier_name TEXT,
    country TEXT
);

CREATE TABLE warehouses (
    warehouse_id TEXT PRIMARY KEY,
    warehouse_name TEXT,
    country TEXT,
    region TEXT
);

CREATE TABLE carrier_costs (
    carrier TEXT,
    country TEXT,
    service TEXT,
    cost_per_shipment REAL,
    PRIMARY KEY(carrier, country, service)
);

CREATE TABLE calendar (
    date TEXT,
    country TEXT,
    is_holiday INTEGER,
    holiday_name TEXT,
    PRIMARY KEY(date, country)
);
