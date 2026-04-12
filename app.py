# =============================================================================
# app.py
# =============================================================================
# This is the MAIN file that runs your entire website and API.
#
# HOW TO START THE SERVER:
#   python3 app.py
#
# HOW TO STOP THE SERVER:
#   Press CTRL + C in the terminal
#
# WHAT IS AN API?
#   An API is a set of URLs your code can call to read or change data.
#   Instead of a human visiting a page, your Python scripts will call
#   these URLs to add products, update prices, etc.
#
# WHAT IS JSON?
#   JSON is the format APIs use to send data back and forth.
#   It looks like this: {"part_number": "DP21074", "price": 850.00}
# =============================================================================

from flask import Flask, request, jsonify, render_template
import sqlite3
import os

# ------------------------------------------------------------------------------
# APP SETUP
# ------------------------------------------------------------------------------

# Create the Flask application - this is the engine that powers everything
app = Flask(__name__)

# The name of our database file
DATABASE = 'products.db'


# ------------------------------------------------------------------------------
# HELPER FUNCTION
# ------------------------------------------------------------------------------

def get_db_connection():
    """
    Opens and returns a connection to the database.
    We call this every time we need to read or write data.
    row_factory makes results come back as dictionaries (name: value)
    instead of plain lists - much easier to work with.
    """
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


# ------------------------------------------------------------------------------
# WEBSITE ROUTES
# A route is a URL. When someone visits that URL the function below it runs.
# ------------------------------------------------------------------------------

@app.route('/')
def home():
    """
    Serves your store's home page.
    Runs when someone visits: http://localhost:5000/
    """
    return render_template('index.html')


# ------------------------------------------------------------------------------
# API — PRODUCTS
# CRUD = Create, Read, Update, Delete
# These are the 4 things you do with any data.
# ------------------------------------------------------------------------------

# ---- READ: Get all products --------------------------------------------------
@app.route('/api/products', methods=['GET'])
def get_all_products():
    """
    GET /api/products
    Returns every active product in the store as a JSON list.
    Test in browser: http://localhost:5000/api/products
    """
    conn = get_db_connection()
    products = conn.execute(
        'SELECT * FROM products WHERE is_active = 1'
    ).fetchall()
    conn.close()

    # Convert each database row into a plain dictionary
    return jsonify([dict(row) for row in products]), 200


# ---- READ: Get one product by part number ------------------------------------
@app.route('/api/products/<part_number>', methods=['GET'])
def get_product(part_number):
    """
    GET /api/products/DP21074
    Returns a single product matching the part number in the URL.
    """
    conn = get_db_connection()
    product = conn.execute(
        'SELECT * FROM products WHERE part_number = ?', (part_number,)
    ).fetchone()
    conn.close()

    if product is None:
        return jsonify({'error': f'Product {part_number} not found'}), 404

    return jsonify(dict(product)), 200


# ---- CREATE: Add a new product -----------------------------------------------
@app.route('/api/products', methods=['POST'])
def add_product():
    """
    POST /api/products
    Adds a new product. Send product details as JSON in the request body.

    Required fields:
        part_number, name, category, vehicle_type, price

    Optional fields:
        description, stock_quantity

    Example JSON to send:
    {
        "part_number": "DP21074",
        "name": "EBC Greenstuff Street Brake Pads",
        "category": "Brake Pads",
        "vehicle_type": "Automotive",
        "price": 850.00,
        "description": "Street pads for everyday driving",
        "stock_quantity": 10
    }
    """
    data = request.get_json()

    # Check all required fields are present before doing anything
    required_fields = ['part_number', 'name', 'category', 'vehicle_type', 'price']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400

    conn = get_db_connection()
    try:
        conn.execute('''
            INSERT INTO products
                (part_number, name, category, vehicle_type, price, description, stock_quantity)
            VALUES
                (?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['part_number'],
            data['name'],
            data['category'],
            data['vehicle_type'],
            data['price'],
            data.get('description', ''),    # Optional - defaults to empty string
            data.get('stock_quantity', 0)   # Optional - defaults to 0
        ))
        conn.commit()
        conn.close()
        return jsonify({'message': f"Product {data['part_number']} added successfully!"}), 201

    except sqlite3.IntegrityError:
        # This fires if the part_number already exists in the database
        conn.close()
        return jsonify({'error': f"Part number {data['part_number']} already exists!"}), 409


# ---- UPDATE: Edit an existing product ----------------------------------------
@app.route('/api/products/<part_number>', methods=['PATCH'])
def update_product(part_number):
    """
    PATCH /api/products/DP21074
    Updates one or more fields on an existing product.
    Only send the fields you want to change.

    Example - update just the price:
    { "price": 920.00 }

    Example - update price and stock:
    { "price": 920.00, "stock_quantity": 5 }
    """
    conn = get_db_connection()

    # Make sure the product exists first
    existing = conn.execute(
        'SELECT * FROM products WHERE part_number = ?', (part_number,)
    ).fetchone()

    if existing is None:
        conn.close()
        return jsonify({'error': f'Product {part_number} not found'}), 404

    data = request.get_json()

    # Only these fields are allowed to be updated
    allowed_fields = ['name', 'category', 'vehicle_type', 'price',
                      'description', 'stock_quantity', 'is_active']

    # Build the SQL update dynamically based on what was sent
    updates = []
    values = []
    for field in allowed_fields:
        if field in data:
            updates.append(f'{field} = ?')
            values.append(data[field])

    if not updates:
        conn.close()
        return jsonify({'error': 'No valid fields provided to update'}), 400

    values.append(part_number)
    sql = f"UPDATE products SET {', '.join(updates)} WHERE part_number = ?"
    conn.execute(sql, values)
    conn.commit()
    conn.close()

    return jsonify({'message': f'Product {part_number} updated successfully!'}), 200


# ---- DELETE: Remove a product ------------------------------------------------
@app.route('/api/products/<part_number>', methods=['DELETE'])
def delete_product(part_number):
    """
    DELETE /api/products/DP21074
    Permanently removes a product from the database.
    """
    conn = get_db_connection()

    existing = conn.execute(
        'SELECT * FROM products WHERE part_number = ?', (part_number,)
    ).fetchone()

    if existing is None:
        conn.close()
        return jsonify({'error': f'Product {part_number} not found'}), 404

    conn.execute('DELETE FROM products WHERE part_number = ?', (part_number,))
    conn.commit()
    conn.close()

    return jsonify({'message': f'Product {part_number} deleted successfully!'}), 200


# ------------------------------------------------------------------------------
# API — VEHICLE FITMENT
# ------------------------------------------------------------------------------

# ---- CREATE: Add a vehicle fitment -------------------------------------------
@app.route('/api/fitment', methods=['POST'])
def add_fitment():
    """
    POST /api/fitment
    Links a product to a vehicle it fits.

    Example JSON:
    {
        "part_number": "DP21074",
        "make": "Toyota",
        "model": "Corolla",
        "year_from": 2015,
        "year_to": 2022,
        "engine_size": "2.0L",
        "axle": "Front",
        "notes": ""
    }
    """
    data = request.get_json()

    required_fields = ['part_number', 'make', 'model']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400

    conn = get_db_connection()
    conn.execute('''
        INSERT INTO vehicle_fitment
            (part_number, make, model, year_from, year_to, engine_size, axle, notes)
        VALUES
            (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data['part_number'],
        data['make'],
        data['model'],
        data.get('year_from'),
        data.get('year_to'),
        data.get('engine_size', ''),
        data.get('axle', ''),
        data.get('notes', '')
    ))
    conn.commit()
    conn.close()

    return jsonify({'message': 'Fitment added successfully!'}), 201


# ---- READ: Get all fitments for a part number --------------------------------
@app.route('/api/fitment/<part_number>', methods=['GET'])
def get_fitment(part_number):
    """
    GET /api/fitment/DP21074
    Returns all vehicles that a specific part fits.
    """
    conn = get_db_connection()
    fitments = conn.execute(
        'SELECT * FROM vehicle_fitment WHERE part_number = ?', (part_number,)
    ).fetchall()
    conn.close()

    return jsonify([dict(row) for row in fitments]), 200


# ------------------------------------------------------------------------------
# START THE SERVER
# ------------------------------------------------------------------------------

if __name__ == '__main__':
    if not os.path.exists(DATABASE):
        print("⚠️  Database not found! Run this first: python3 database.py")
    else:
        print("✅ Database found!")
        print("🚀 Server is starting...")
        print("🌐 Visit your store: http://localhost:5000")
        print("📦 API endpoint:     http://localhost:5000/api/products")
        print("⛔ To stop:          Press CTRL + C\n")

    app.run(debug=True, port=5000)