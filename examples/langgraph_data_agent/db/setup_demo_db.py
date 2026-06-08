from datetime import date, timedelta
from pathlib import Path
import sqlite3

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "shipments.db"
SCHEMA_PATH = Path(__file__).with_name("schema.sql")

SERVICE_CONFIG = ["STANDARD", "EXPRESS", "DROPPOINT"]
SERVICE_COST_MULTIPLIER = {"STANDARD": 1.0, "EXPRESS": 1.45, "DROPPOINT": 0.72}

COUNTRY_CONFIG = {
    "IT": {
        "warehouses": [
            ("WH_IT_NORTH", "Italy North Warehouse", "north", "MILAN"),
            ("WH_IT_SOUTH", "Italy South Warehouse", "south", "NAPLES"),
            ("WH_IT_CENTER", "Italy Center Warehouse", "center", "ROME"),
        ],
        "carriers": ["DHL", "UPS", "BRT", "POSTE_IT", "SDA", "GLS_IT"],
        "carrier_weights": [16, 13, 22, 19, 14, 16],
        "rows_base": 128,
    },
    "ES": {
        "warehouses": [
            ("WH_ES_CENTER", "Spain Center Warehouse", "center", "MADRID"),
            ("WH_ES_NORTH", "Spain North Warehouse", "north", "BILBAO"),
            ("WH_ES_EAST", "Spain East Warehouse", "east", "BARCELONA"),
            ("WH_ES_SOUTH", "Spain South Warehouse", "south", "SEVILLA"),
        ],
        "carriers": ["DHL", "UPS", "SEUR", "CORREOS", "MRW", "NACEX", "GLS_ES"],
        "carrier_weights": [11, 9, 18, 24, 14, 10, 14],
        "rows_base": 156,
    },
    "FR": {
        "warehouses": [
            ("WH_FR_NORTH", "France North Warehouse", "north", "LILLE"),
            ("WH_FR_SOUTH", "France South Warehouse", "south", "MARSEILLE"),
            ("WH_FR_PARIS", "France Paris Warehouse", "paris", "PARIS"),
        ],
        "carriers": ["DHL", "UPS", "COLISSIMO", "CHRONOPOST", "DPD_FR", "MONDIAL_RELAY"],
        "carrier_weights": [12, 10, 25, 18, 17, 18],
        "rows_base": 138,
    },
}

CARRIER_NAMES = {
    "DHL": ("DHL Express", "GLOBAL"),
    "UPS": ("United Parcel Service", "GLOBAL"),
    "BRT": ("BRT Bartolini", "IT"),
    "POSTE_IT": ("Poste Italiane", "IT"),
    "SDA": ("SDA Express Courier", "IT"),
    "GLS_IT": ("GLS Italy", "IT"),
    "SEUR": ("SEUR", "ES"),
    "CORREOS": ("Correos", "ES"),
    "MRW": ("MRW", "ES"),
    "NACEX": ("NACEX", "ES"),
    "GLS_ES": ("GLS Spain", "ES"),
    "COLISSIMO": ("Colissimo", "FR"),
    "CHRONOPOST": ("Chronopost", "FR"),
    "DPD_FR": ("DPD France", "FR"),
    "MONDIAL_RELAY": ("Mondial Relay", "FR"),
}

DELAY_RATE = {
    "DHL": 18,
    "UPS": 22,
    "BRT": 31,
    "POSTE_IT": 16,
    "SDA": 27,
    "GLS_IT": 24,
    "SEUR": 21,
    "CORREOS": 17,
    "MRW": 29,
    "NACEX": 13,
    "GLS_ES": 33,
    "COLISSIMO": 19,
    "CHRONOPOST": 15,
    "DPD_FR": 26,
    "MONDIAL_RELAY": 30,
}

POTENTIAL_RATE = {
    "DHL": 5,
    "UPS": 6,
    "BRT": 8,
    "POSTE_IT": 5,
    "SDA": 7,
    "GLS_IT": 8,
    "SEUR": 6,
    "CORREOS": 5,
    "MRW": 8,
    "NACEX": 4,
    "GLS_ES": 9,
    "COLISSIMO": 5,
    "CHRONOPOST": 4,
    "DPD_FR": 7,
    "MONDIAL_RELAY": 8,
}


def setup_demo_db(db_path: Path = DB_PATH) -> Path:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.executemany("INSERT INTO carriers VALUES (?, ?, ?)", carrier_rows())
    conn.executemany("INSERT INTO warehouses VALUES (?, ?, ?, ?)", warehouse_rows())

    orders, shipments, events = build_demo_rows()
    conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?)", orders)
    conn.executemany("INSERT INTO shipments VALUES (?, ?, ?, ?, ?, ?, ?)", shipments)
    conn.executemany("INSERT INTO tracking_events VALUES (?, ?, ?, ?, ?)", events)
    conn.executemany("INSERT INTO carrier_costs VALUES (?, ?, ?, ?)", cost_rows())
    conn.executemany("INSERT INTO calendar VALUES (?, ?, ?, ?)", build_calendar_rows())
    conn.commit()
    conn.close()
    return db_path


def carrier_rows() -> list[tuple[str, str, str]]:
    rows = []
    seen = set()
    for config in COUNTRY_CONFIG.values():
        for carrier in config["carriers"]:
            if carrier in seen:
                continue
            carrier_name, country = CARRIER_NAMES[carrier]
            rows.append((carrier, carrier_name, country))
            seen.add(carrier)
    return sorted(rows)


def warehouse_rows() -> list[tuple[str, str, str, str]]:
    rows = []
    for country, config in COUNTRY_CONFIG.items():
        for warehouse_id, warehouse_name, region, _city in config["warehouses"]:
            rows.append((warehouse_id, warehouse_name, country, region))
    return rows


def cost_rows() -> list[tuple[str, str, str, float]]:
    rows = []
    for country, config in COUNTRY_CONFIG.items():
        for carrier_index, carrier in enumerate(config["carriers"]):
            base_cost = 2.05 + ((carrier_index * 37 + len(country) * 11) % 95) / 100
            for service in SERVICE_CONFIG:
                cost = round(base_cost * SERVICE_COST_MULTIPLIER[service], 2)
                rows.append((carrier, country, service, cost))
    return rows


def build_demo_rows() -> tuple[list[tuple], list[tuple], list[tuple]]:
    orders = []
    shipments = []
    events = []
    order_id = 1
    event_id = 1
    promised_dates = [date(2026, 6, 1) + timedelta(days=offset) for offset in range(18)]

    for country_index, (country, config) in enumerate(COUNTRY_CONFIG.items()):
        for promised_idx, promised_date in enumerate(promised_dates):
            rows_for_day = config["rows_base"] + ((promised_idx * 7 + country_index * 9) % 17)
            for row_idx in range(rows_for_day):
                carrier = weighted_choice(
                    config["carriers"],
                    config["carrier_weights"],
                    row_idx * 13 + promised_idx * 17 + country_index * 19,
                )
                service = service_for(row_idx, promised_idx, country_index)
                warehouse_id, _warehouse_name, _region, city = config["warehouses"][
                    (row_idx + promised_idx) % len(config["warehouses"])
                ]
                order_code = f"O{order_id:05d}"
                shipment_code = f"S{order_id:05d}"
                order_date = promised_date - timedelta(days=1 + ((row_idx + country_index) % 4))
                order_value = round(28.5 + ((order_id * 23 + row_idx * 11) % 680) * 1.07, 2)
                delivered_date, status, outcome = delivery_outcome(
                    carrier,
                    promised_date,
                    row_idx,
                    promised_idx,
                    country_index,
                )

                orders.append(
                    (
                        order_code,
                        iso(order_date),
                        country,
                        iso(promised_date),
                        service,
                        order_value,
                    )
                )
                shipments.append(
                    (
                        shipment_code,
                        order_code,
                        carrier,
                        warehouse_id,
                        iso(order_date),
                        iso(delivered_date) if delivered_date else None,
                        status,
                    )
                )
                event_id = add_tracking_events(
                    events,
                    event_id,
                    shipment_code,
                    warehouse_id,
                    city,
                    order_date,
                    promised_date,
                    delivered_date,
                    status,
                    outcome,
                )
                order_id += 1
    return orders, shipments, events


def weighted_choice(items: list[str], weights: list[int], seed: int) -> str:
    total = sum(weights)
    bucket = seed % total
    running = 0
    for item, weight in zip(items, weights, strict=True):
        running += weight
        if bucket < running:
            return item
    return items[-1]


def service_for(row_idx: int, promised_idx: int, country_index: int) -> str:
    score = (row_idx * 5 + promised_idx * 3 + country_index * 7) % 100
    if score < 48:
        return "STANDARD"
    if score < 76:
        return "EXPRESS"
    return "DROPPOINT"


def delivery_outcome(
    carrier: str,
    promised_date: date,
    row_idx: int,
    promised_idx: int,
    country_index: int,
) -> tuple[date | None, str, str]:
    score = (row_idx * 29 + promised_idx * 31 + country_index * 37 + len(carrier) * 7) % 100
    potential_cutoff = POTENTIAL_RATE[carrier]
    late_cutoff = potential_cutoff + DELAY_RATE[carrier]
    if score < potential_cutoff:
        return None, "IN_TRANSIT", "potential_late"
    if score < late_cutoff:
        days_late = 1 + ((score + row_idx + promised_idx) % 3)
        return promised_date + timedelta(days=days_late), "DELIVERED", "late"
    if score > 93:
        return promised_date - timedelta(days=1), "DELIVERED", "early"
    return promised_date, "DELIVERED", "on_time"


def add_tracking_events(
    events: list[tuple],
    event_id: int,
    shipment_code: str,
    warehouse_id: str,
    city: str,
    order_date: date,
    promised_date: date,
    delivered_date: date | None,
    status: str,
    outcome: str,
) -> int:
    events.append((f"E{event_id:05d}", shipment_code, f"{iso(order_date)} 09:00", "PICKED_UP", warehouse_id))
    event_id += 1
    if outcome in {"late", "potential_late"}:
        events.append(
            (f"E{event_id:05d}", shipment_code, f"{iso(promised_date)} 18:30", "EXCEPTION", city)
        )
        event_id += 1
    if status == "DELIVERED":
        events.append(
            (f"E{event_id:05d}", shipment_code, f"{iso(delivered_date)} 11:00", "DELIVERED", city)
        )
        event_id += 1
    else:
        events.append(
            (
                f"E{event_id:05d}",
                shipment_code,
                f"{iso(promised_date + timedelta(days=1))} 10:15",
                "IN_TRANSIT",
                city,
            )
        )
        event_id += 1
    return event_id


def build_calendar_rows() -> list[tuple[str, str, int, str | None]]:
    rows = []
    start = date(2026, 5, 25)
    for offset in range(35):
        current = start + timedelta(days=offset)
        for country in COUNTRY_CONFIG:
            is_sunday = current.weekday() == 6
            holiday_name = "Sunday" if is_sunday else None
            if country == "FR" and current == date(2026, 6, 8):
                holiday_name = "Demo regional holiday"
            if country == "ES" and current == date(2026, 6, 13):
                holiday_name = "Demo local holiday"
            rows.append((iso(current), country, int(holiday_name is not None), holiday_name))
    return rows


def iso(value: date) -> str:
    return value.isoformat()


if __name__ == "__main__":
    print(setup_demo_db())
