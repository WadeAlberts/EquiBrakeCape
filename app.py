# =============================================================================
# app.py
# =============================================================================
# Main server file - runs the website and all API endpoints.
# Start with: python3 app.py
# Stop with:  CTRL + C
# =============================================================================

from flask import Flask, request, jsonify, render_template
import sqlite3
import os

# ------------------------------------------------------------------------------
# APP SETUP
# ------------------------------------------------------------------------------

app = Flask(__name__)
DATABASE = 'products.db'


# ------------------------------------------------------------------------------
# HELPER FUNCTION
# ------------------------------------------------------------------------------

def get_db_connection():
    """
    Opens a connection to the database.
    row_factory makes results come back as dictionaries (name: value pairs).
    """
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


# ==============================================================================
# WEBSITE PAGE ROUTES
# These serve actual HTML pages that customers see in their browser.
# ==============================================================================

@app.route('/')
def home():
    """
    Serves the home page.
    URL: http://localhost:5000/
    """
    return render_template('index.html')


@app.route('/results')
def results():
    """
    Serves the search results page.
    Customers land here after using the vehicle finder.
    URL: http://localhost:5000/results?make=Toyota&model=Corolla&year=2018&engine=2.0L

    The ?make=Toyota&model=Corolla part is called a "query string".
    Flask reads these values using request.args.get()
    """
    # Read the search values from the URL query string
    make   = request.args.get('make', '').strip()
    model  = request.args.get('model', '').strip()
    year   = request.args.get('year', '').strip()
    engine = request.args.get('engine', '').strip()

    # If nothing was searched, send them back to home
    if not make:
        return render_template('index.html')

    conn = get_db_connection()

    # Build the SQL query dynamically based on what was provided
    # We always need at least make and model
    # Year and engine are optional refinements
    sql = '''
        SELECT DISTINCT
            p.part_number,
            p.category,
            p.srp_incl_vat,
            p.srp_excl_vat,
            vf.product_type,
            vf.position,
            v.make,
            v.model,
            v.sub_model,
            v.year,
            v.engine,
            v.front_caliper_type,
            v.rear_caliper_type
        FROM vehicle_fitment vf
        JOIN vehicles v  ON vf.vehicle_id  = v.id
        JOIN products p  ON vf.part_number = p.part_number
        WHERE v.make  = ?
          AND v.model = ?
    '''
    params = [make, model]

    # Only filter by year if one was provided
    if year:
        sql += ' AND v.year = ?'
        params.append(year)

    # Only filter by engine if one was provided
    if engine:
        sql += ' AND v.engine = ?'
        params.append(engine)

    sql += ' ORDER BY p.category, vf.position'

    parts = conn.execute(sql, params).fetchall()
    conn.close()

    # Convert to list of dictionaries for easy use in the HTML template
    parts_list = [dict(row) for row in parts]

    # Group parts by category so we can display them in sections
    # e.g. all "Brake Pads" together, all "Brake Discs" together
    grouped = {}
    for part in parts_list:
        cat = part['category'] or 'Other'
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append(part)

    return render_template('results.html',
        grouped_parts = grouped,
        make          = make,
        model         = model,
        year          = year,
        engine        = engine,
        total_results = len(parts_list)
    )


# ==============================================================================
# API ROUTES — VEHICLE FINDER DROPDOWNS
# These power the cascading dropdowns on the home page.
# Each one depends on what was selected before it.
# ==============================================================================

@app.route('/api/makes', methods=['GET'])
def get_makes():
    """
    GET /api/makes
    Returns all unique vehicle makes in alphabetical order.
    This populates the first dropdown on the vehicle finder.
    Example response: ["Alfa Romeo", "Audi", "BMW", "Ford", ...]
    """
    conn = get_db_connection()
    rows = conn.execute(
        'SELECT DISTINCT make FROM vehicles WHERE make IS NOT NULL ORDER BY make'
    ).fetchall()
    conn.close()
    return jsonify([row['make'] for row in rows]), 200


@app.route('/api/models', methods=['GET'])
def get_models():
    """
    GET /api/models?make=Toyota
    Returns all unique models for a given make.
    Populates the Model dropdown after a Make is selected.
    """
    make = request.args.get('make', '').strip()
    if not make:
        return jsonify({'error': 'make parameter is required'}), 400

    conn = get_db_connection()
    rows = conn.execute(
        'SELECT DISTINCT model FROM vehicles WHERE make = ? AND model IS NOT NULL ORDER BY model',
        (make,)
    ).fetchall()
    conn.close()
    return jsonify([row['model'] for row in rows]), 200


@app.route('/api/years', methods=['GET'])
def get_years():
    """
    GET /api/years?make=Toyota&model=Corolla
    Returns all unique years for a given make and model.
    Populates the Year dropdown after Make and Model are selected.
    """
    make  = request.args.get('make', '').strip()
    model = request.args.get('model', '').strip()

    if not make or not model:
        return jsonify({'error': 'make and model parameters are required'}), 400

    conn = get_db_connection()
    rows = conn.execute(
        '''SELECT DISTINCT year FROM vehicles
           WHERE make = ? AND model = ? AND year IS NOT NULL
           ORDER BY year''',
        (make, model)
    ).fetchall()
    conn.close()
    return jsonify([row['year'] for row in rows]), 200


@app.route('/api/engines', methods=['GET'])
def get_engines():
    """
    GET /api/engines?make=Toyota&model=Corolla&year=2018
    Returns all unique engine sizes for a given make, model and year.
    Populates the Engine dropdown after Make, Model and Year are selected.
    """
    make  = request.args.get('make', '').strip()
    model = request.args.get('model', '').strip()
    year  = request.args.get('year', '').strip()

    if not make or not model:
        return jsonify({'error': 'make and model parameters are required'}), 400

    conn = get_db_connection()

    # Year is optional - if not provided, return all engines for make+model
    if year:
        rows = conn.execute(
            '''SELECT DISTINCT engine FROM vehicles
               WHERE make = ? AND model = ? AND year = ? AND engine IS NOT NULL
               ORDER BY engine''',
            (make, model, year)
        ).fetchall()
    else:
        rows = conn.execute(
            '''SELECT DISTINCT engine FROM vehicles
               WHERE make = ? AND model = ? AND engine IS NOT NULL
               ORDER BY engine''',
            (make, model)
        ).fetchall()

    conn.close()
    return jsonify([row['engine'] for row in rows]), 200


@app.route('/api/categories', methods=['GET'])
def get_categories():
    """
    GET /api/categories
    Returns all unique product categories and their counts.
    Used to build the category browser section on the home page.
    """
    conn = get_db_connection()
    rows = conn.execute(
        '''SELECT category, COUNT(*) as count
           FROM products
           WHERE category IS NOT NULL
           GROUP BY category
           ORDER BY count DESC'''
    ).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows]), 200


# ==============================================================================
# API ROUTES — PRODUCTS (admin use)
# ==============================================================================

@app.route('/api/products', methods=['GET'])
def get_all_products():
    """
    GET /api/products
    Returns all products. Supports optional category filter.
    Example: /api/products?category=Brake Pads
    """
    category = request.args.get('category', '').strip()
    conn = get_db_connection()

    if category:
        products = conn.execute(
            'SELECT * FROM products WHERE category = ? ORDER BY part_number',
            (category,)
        ).fetchall()
    else:
        products = conn.execute(
            'SELECT * FROM products ORDER BY part_number'
        ).fetchall()

    conn.close()
    return jsonify([dict(row) for row in products]), 200


@app.route('/api/products/<part_number>', methods=['GET'])
def get_product(part_number):
    """
    GET /api/products/DP21074
    Returns a single product by part number.
    Also includes all vehicles it fits.
    """
    conn = get_db_connection()

    product = conn.execute(
        'SELECT * FROM products WHERE part_number = ?', (part_number,)
    ).fetchone()

    if product is None:
        conn.close()
        return jsonify({'error': f'Product {part_number} not found'}), 404

    # Also get all vehicles this part fits
    fitments = conn.execute(
        '''SELECT v.make, v.model, v.sub_model, v.year, v.engine, vf.position
           FROM vehicle_fitment vf
           JOIN vehicles v ON vf.vehicle_id = v.id
           WHERE vf.part_number = ?
           ORDER BY v.make, v.model, v.year''',
        (part_number,)
    ).fetchall()

    conn.close()

    result = dict(product)
    result['fits'] = [dict(row) for row in fitments]
    return jsonify(result), 200


@app.route('/api/products', methods=['POST'])
def add_product():
    """
    POST /api/products
    Manually adds a single product.
    Required fields: part_number, category
    """
    data = request.get_json()
    if 'part_number' not in data:
        return jsonify({'error': 'part_number is required'}), 400

    conn = get_db_connection()
    try:
        conn.execute('''
            INSERT INTO products (part_number, category, srp_excl_vat, srp_incl_vat,
                                  dealer1_price, dealer2_price, dealer3_price)
            VALUES (:part_number, :category, :srp_excl_vat, :srp_incl_vat,
                    :dealer1_price, :dealer2_price, :dealer3_price)
        ''', {
            'part_number'  : data.get('part_number'),
            'category'     : data.get('category', 'Other'),
            'srp_excl_vat' : data.get('srp_excl_vat'),
            'srp_incl_vat' : data.get('srp_incl_vat'),
            'dealer1_price': data.get('dealer1_price'),
            'dealer2_price': data.get('dealer2_price'),
            'dealer3_price': data.get('dealer3_price'),
        })
        conn.commit()
        conn.close()
        return jsonify({'message': f"Product {data['part_number']} added!"}), 201
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': f"Part number already exists"}), 409


@app.route('/api/products/<part_number>', methods=['PATCH'])
def update_product(part_number):
    """
    PATCH /api/products/DP21074
    Updates one or more fields on an existing product.
    Only send the fields you want to change.
    """
    conn = get_db_connection()
    existing = conn.execute(
        'SELECT * FROM products WHERE part_number = ?', (part_number,)
    ).fetchone()

    if existing is None:
        conn.close()
        return jsonify({'error': f'Product {part_number} not found'}), 404

    data = request.get_json()
    allowed = ['category', 'description', 'srp_excl_vat', 'srp_incl_vat',
               'dealer1_price', 'dealer2_price', 'dealer3_price']

    updates = []
    values  = []
    for field in allowed:
        if field in data:
            updates.append(f'{field} = ?')
            values.append(data[field])

    if not updates:
        conn.close()
        return jsonify({'error': 'No valid fields to update'}), 400

    values.append(part_number)
    conn.execute(f"UPDATE products SET {', '.join(updates)} WHERE part_number = ?", values)
    conn.commit()
    conn.close()
    return jsonify({'message': f'Product {part_number} updated!'}), 200


@app.route('/api/products/<part_number>', methods=['DELETE'])
def delete_product(part_number):
    """
    DELETE /api/products/DP21074
    Permanently removes a product.
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
    return jsonify({'message': f'Product {part_number} deleted!'}), 200


# ==============================================================================
# START SERVER
# ==============================================================================

if __name__ == '__main__':
    if not os.path.exists(DATABASE):
        print("⚠️  Database not found! Run: python3 database.py")
    else:
        print("✅ Database found!")
        print("🚀 Starting Equi Brake Cape server...")
        print("🌐 Store:  http://localhost:5000")
        print("📦 API:    http://localhost:5000/api/products")
        print("⛔ Stop:   CTRL + C\n")

    app.run(debug=True, port=5000)