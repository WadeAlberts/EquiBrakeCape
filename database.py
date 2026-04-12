# =============================================================================
# database.py
# =============================================================================
# This file creates your database and all the tables inside it.
# Think of the database like an Excel file.
# Think of each table like a separate sheet inside that Excel file.
#
# Run this file ONCE to set up your database before starting the server.
# Command: python3 database.py
# =============================================================================

import sqlite3  # Built into Python - no installation needed


def create_database():
    """
    Creates the database file 'products.db' and all tables inside it.
    Safe to run multiple times - it will never overwrite existing data.
    """

    # Connect to the database file.
    # If the file doesn't exist yet, SQLite creates it automatically.
    connection = sqlite3.connect('products.db')

    # A cursor is the tool we use to send instructions to the database.
    cursor = connection.cursor()

    # -------------------------------------------------------------------------
    # TABLE 1: products
    # Stores every product you sell.
    # Each row = one product.
    # -------------------------------------------------------------------------
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            part_number      TEXT    NOT NULL UNIQUE,
            name             TEXT    NOT NULL,
            category         TEXT    NOT NULL,
            vehicle_type     TEXT    NOT NULL,
            price            REAL    NOT NULL,
            description      TEXT,
            stock_quantity   INTEGER DEFAULT 0,
            is_active        INTEGER DEFAULT 1
        )
    ''')
    # Column explanations:
    # id             - A unique number automatically assigned to each product
    # part_number    - EBC's part number e.g. "DP21074" - must be unique
    # name           - Product name e.g. "EBC Greenstuff Brake Pads"
    # category       - e.g. "Brake Pads", "Brake Discs", "Brake Lines"
    # vehicle_type   - e.g. "Automotive", "Motorcycle", "Racing"
    # price          - Price in Rands e.g. 850.00
    # description    - Optional longer description
    # stock_quantity - How many units in stock (starts at 0)
    # is_active      - 1 = visible in store | 0 = hidden from store

    # -------------------------------------------------------------------------
    # TABLE 2: vehicle_fitment
    # Links a product to the vehicles it fits.
    # One product can fit many vehicles so this lives in its own table.
    # -------------------------------------------------------------------------
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vehicle_fitment (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            part_number   TEXT    NOT NULL,
            make          TEXT    NOT NULL,
            model         TEXT    NOT NULL,
            year_from     INTEGER,
            year_to       INTEGER,
            engine_size   TEXT,
            axle          TEXT,
            notes         TEXT
        )
    ''')
    # Column explanations:
    # part_number  - Links to the product e.g. "DP21074"
    # make         - Vehicle brand e.g. "Toyota", "BMW", "Honda"
    # model        - e.g. "Corolla", "3 Series", "CBR600"
    # year_from    - Year fitment starts e.g. 2015
    # year_to      - Year fitment ends e.g. 2022
    # engine_size  - e.g. "2.0L", "600cc"
    # axle         - e.g. "Front", "Rear", "Both"
    # notes        - Any extra fitment information

    # Save everything and close the connection
    connection.commit()
    connection.close()

    print("✅ Database created successfully! File 'products.db' is ready.")


# Only runs when you execute this file directly
if __name__ == '__main__':
    create_database()