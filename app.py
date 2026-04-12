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
    category =