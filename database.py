# =============================================================================
# database.py
# =============================================================================
# Creates the database and ALL tables.
# Run this ONCE on a fresh start — it wipes and recreates all tables.
#
# Command: python3 database.py
#
# PHASE 5 CHANGES (PayFast):
#   - orders table has 2 new columns:
#       payment_status     - tracks PayFast payment state
#       payfast_payment_id - the ID PayFast gives us when payment completes
#                           (sent in the ITN as 'pf_payment_id')
# =============================================================================

import sqlite3


def create_database():
    """
    Creates products.db with 5 tables:
    1. vehicles        - every vehicle from the catalogue
    2. products        - every EBC part number with pricing
    3. vehicle_fitment - links vehicles to parts that fit them
    4. orders          - every customer order placed
    5. order_items     - every line item within an order
    """

    connection = sqlite3.connect('products.db')
    cursor = connection.cursor()

    # -------------------------------------------------------------------------
    # Drop all tables cleanly (order matters because of foreign keys)
    # -------------------------------------------------------------------------
    cursor.execute('DROP TABLE IF EXISTS order_items')
    cursor.execute('DROP TABLE IF EXISTS orders')
    cursor.execute('DROP TABLE IF EXISTS vehicle_fitment')
    cursor.execute('DROP TABLE IF EXISTS products')
    cursor.execute('DROP TABLE IF EXISTS vehicles')

    # -------------------------------------------------------------------------
    # TABLE 1: vehicles
    # -------------------------------------------------------------------------
    cursor.execute('''
        CREATE TABLE vehicles (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            make                 TEXT,
            model                TEXT,
            sub_model            TEXT,
            engine               TEXT,
            engine_type          TEXT,
            valves               TEXT,
            bhp                  TEXT,
            year                 TEXT,
            special_comments     TEXT,
            front_caliper_type   TEXT,
            front_solid_vented   TEXT,
            front_bolt_holes     TEXT,
            front_diameter       TEXT,
            front_total_height   TEXT,
            front_thickness      TEXT,
            front_shoe_type      TEXT,
            rear_caliper_type    TEXT,
            rear_solid_vented    TEXT,
            rear_bolt_holes      TEXT,
            rear_diameter        TEXT,
            rear_total_height    TEXT,
            rear_thickness       TEXT,
            rear_shoe_type       TEXT
        )
    ''')

    # -------------------------------------------------------------------------
    # TABLE 2: products
    # -------------------------------------------------------------------------
    cursor.execute('''
        CREATE TABLE products (
            part_number      TEXT PRIMARY KEY,
            description      TEXT,
            category         TEXT,
            dealer1_price    REAL,
            dealer2_price    REAL,
            dealer3_price    REAL,
            srp_excl_vat     REAL,
            srp_incl_vat     REAL
        )
    ''')

    # -------------------------------------------------------------------------
    # TABLE 3: vehicle_fitment
    # -------------------------------------------------------------------------
    cursor.execute('''
        CREATE TABLE vehicle_fitment (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id    INTEGER NOT NULL,
            part_number   TEXT    NOT NULL,
            product_type  TEXT,
            position      TEXT,
            FOREIGN KEY (vehicle_id) REFERENCES vehicles(id)
        )
    ''')

    # -------------------------------------------------------------------------
    # TABLE 4: orders
    # One row per customer order.
    #
    # PHASE 5 COLUMNS:
    #   payment_status     - tracks where we are in the payment process:
    #                          "pending_payment" = order saved, waiting for PayFast
    #                          "paid"            = PayFast ITN confirmed payment ✅
    #                          "cancelled"       = customer cancelled on PayFast ❌
    #                          "failed"          = payment failed on PayFast ⚠️
    #   payfast_payment_id - PayFast's own payment ID (sent in the ITN as pf_payment_id)
    #                        Useful for reconciling payments in your PayFast dashboard
    # -------------------------------------------------------------------------
    cursor.execute('''
        CREATE TABLE orders (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            order_number        TEXT    NOT NULL UNIQUE,
            status              TEXT    DEFAULT 'pending',
            payment_status      TEXT    DEFAULT 'pending_payment',
            payfast_payment_id  TEXT,
            customer_name       TEXT    NOT NULL,
            customer_email      TEXT    NOT NULL,
            customer_phone      TEXT,
            delivery_address    TEXT    NOT NULL,
            delivery_city       TEXT    NOT NULL,
            delivery_province   TEXT    NOT NULL,
            delivery_postcode   TEXT    NOT NULL,
            order_notes         TEXT,
            subtotal            REAL    NOT NULL,
            vat_amount          REAL    NOT NULL,
            delivery_fee        REAL    NOT NULL DEFAULT 0,
            total_amount        REAL    NOT NULL,
            created_at          TEXT    DEFAULT (datetime('now', 'localtime'))
        )
    ''')

    # -------------------------------------------------------------------------
    # TABLE 5: order_items
    # One row per product line within an order.
    # -------------------------------------------------------------------------
    cursor.execute('''
        CREATE TABLE order_items (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id      INTEGER NOT NULL,
            part_number   TEXT    NOT NULL,
            product_type  TEXT,
            category      TEXT,
            quantity      INTEGER NOT NULL DEFAULT 1,
            unit_price    REAL    NOT NULL,
            line_total    REAL    NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(id)
        )
    ''')

    connection.commit()
    connection.close()

    print("✅ Database created with 5 tables:")
    print("   - vehicles")
    print("   - products")
    print("   - vehicle_fitment")
    print("   - orders  (+ payment_status + payfast_payment_id columns)")
    print("   - order_items")
    print("\nNext steps:")
    print("  1. python3 import_prices.py")
    print("  2. python3 import_catalogue.py")


if __name__ == '__main__':
    create_database()