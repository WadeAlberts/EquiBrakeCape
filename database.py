# =============================================================================
# database.py
# =============================================================================
# Creates the database and all 3 tables we need.
# Run this ONCE before starting the server.
# Command: python3 database.py
#
# WARNING: Running this file will DROP (delete) and recreate all tables.
# Only run it on a fresh start or when you want to wipe all data.
# =============================================================================

import sqlite3


def create_database():
    """
    Creates products.db with 3 tables:
    1. vehicles       - every vehicle from the catalogue
    2. products       - every EBC part number with pricing
    3. vehicle_fitment - links vehicles to the parts that fit them
    """

    connection = sqlite3.connect('products.db')
    cursor = connection.cursor()

    # -------------------------------------------------------------------------
    # Drop tables if they already exist (clean slate)
    # -------------------------------------------------------------------------
    cursor.execute('DROP TABLE IF EXISTS vehicle_fitment')
    cursor.execute('DROP TABLE IF EXISTS products')
    cursor.execute('DROP TABLE IF EXISTS vehicles')

    # -------------------------------------------------------------------------
    # TABLE 1: vehicles
    # One row per vehicle from the Vehicle Catalogue.
    # Stores the vehicle identity and disc/caliper specs.
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
    # Column explanations:
    # make/model/sub_model   - e.g. Toyota / Corolla / Verso
    # engine                 - e.g. 2.0L
    # engine_type            - e.g. Petrol, Diesel
    # valves                 - number of valves
    # bhp                    - brake horsepower
    # year                   - e.g. 2015-2022 or just 2018
    # special_comments       - any notes from EBC catalogue
    # front/rear_caliper     - caliper brand/type
    # front/rear_solid_vented- whether disc is solid or vented
    # front/rear_bolt_holes  - number of bolt holes on disc
    # front/rear_diameter    - disc diameter in mm
    # front/rear_total_height- disc total height
    # front/rear_thickness   - disc thickness new/minimum
    # front/rear_shoe_type   - brake shoe type if applicable

    # -------------------------------------------------------------------------
    # TABLE 2: products
    # One row per EBC part number.
    # Pricing comes from the RSA Dealer Pricelist.
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
    # Column explanations:
    # part_number    - EBC part number e.g. "DP21074" - unique identifier
    # description    - what the product is e.g. "EBC Greenstuff Front Pads"
    # category       - e.g. "Brake Pads", "Brake Discs", "Brake Lines", "Kit"
    # dealer1_price  - price less 15% excl VAT (your dealer tier 1 cost)
    # dealer2_price  - price less 20% excl VAT (your dealer tier 2 cost)
    # dealer3_price  - price less 30% excl VAT (your dealer tier 3 cost)
    # srp_excl_vat   - suggested retail price excluding VAT
    # srp_incl_vat   - suggested retail price including VAT (what customer pays)

    # -------------------------------------------------------------------------
    # TABLE 3: vehicle_fitment
    # Links a vehicle to a part number.
    # One row = "this part fits this vehicle in this position"
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
    # Column explanations:
    # vehicle_id    - links to the vehicles table (the car/bike this fits)
    # part_number   - links to the products table (the EBC part)
    # product_type  - the column name from the catalogue
    #                 e.g. "EBC Greenstuff Front Pads"
    # position      - "Front", "Rear", "Both", or blank
    #                 extracted automatically from the product_type name

    connection.commit()
    connection.close()

    print("✅ Database created with 3 tables: vehicles, products, vehicle_fitment")
    print("📄 File saved as: products.db")
    print("\nNext steps:")
    print("  1. python3 import_prices.py        (import pricing from File 2)")
    print("  2. python3 import_catalogue.py     (import vehicles and fitment from File 1)")


if __name__ == '__main__':
    create_database()