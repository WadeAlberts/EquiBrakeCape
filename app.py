# =============================================================================
# app.py
# =============================================================================
# Main server - runs the website and all API endpoints.
# Start: python3 app.py
# Stop:  CTRL + C
# =============================================================================

from flask import Flask, request, jsonify, render_template, session
import sqlite3
import os
import smtplib                          # Built into Python - sends emails
from email.mime.text import MIMEText    # Formats the email content
from datetime import datetime           # For generating order numbers

# ------------------------------------------------------------------------------
# APP SETUP
# ------------------------------------------------------------------------------

app = Flask(__name__)

# Secret key - Flask uses this to encrypt the session cookie (the cart)
# In production this should be a long random string kept secret
# For now this is fine for local development
app.secret_key = 'equibrakecape-dev-secret-key-2025'

DATABASE = 'products.db'

# ------------------------------------------------------------------------------
# EMAIL CONFIGURATION
# For local testing we send to Python's built-in debugging server.
# To use it, open a second terminal and run:
#   python3 -m smtpd -n -c DebuggingServer localhost:1025
# You will see emails printed there instead of actually being sent.
# ------------------------------------------------------------------------------
EMAIL_HOST     = 'localhost'
EMAIL_PORT     = 1025
EMAIL_FROM     = 'orders@equibrakecape.co.za'
STORE_NAME     = 'Equi Brake Cape'


# ------------------------------------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------------------------------------

def get_db_connection():
    """Opens a database connection with dictionary-style results."""
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def format_currency(amount):
    """
    Formats a number as South African Rand.
    e.g. 1250.50 becomes R1 250.50
    The space is the SA thousands separator.
    """
    if amount is None:
        return 'R0.00'
    # Format with comma first, then replace comma with space
    formatted = f"{amount:,.2f}".replace(',', ' ')
    return f"R{formatted}"


def generate_order_number():
    """
    Generates a unique order number based on date and a sequence.
    e.g. EBC-20250413-0042
    """
    today = datetime.now().strftime('%Y%m%d')
    conn  = get_db_connection()

    # Count how many orders exist for today to generate the sequence number
    count = conn.execute(
        "SELECT COUNT(*) as c FROM orders WHERE order_number LIKE ?",
        (f'EBC-{today}-%',)
    ).fetchone()['c']

    conn.close()
    # Pad the sequence number to 4 digits e.g. 0001, 0042
    return f"EBC-{today}-{str(count + 1).zfill(4)}"


def send_order_email(order, items):
    """
    Sends an order confirmation email to the customer.
    During development this prints to the smtpd debugging server terminal.

    order - the order dictionary
    items - list of order item dictionaries
    """
    try:
        # Build the email body as plain text
        items_text = "\n".join([
            f"  {item['part_number']} x{item['quantity']} — {format_currency(item['line_total'])}"
            for item in items
        ])

        body = f"""
Dear {order['customer_name']},

Thank you for your order with {STORE_NAME}!

ORDER DETAILS
=============
Order Number : {order['order_number']}
Date         : {order['created_at']}
Status       : Order Received

ITEMS ORDERED
=============
{items_text}

ORDER TOTAL
===========
Subtotal     : {format_currency(order['subtotal'])}
VAT (15%)    : {format_currency(order['vat_amount'])}
Delivery     : {format_currency(order['delivery_fee'])}
TOTAL        : {format_currency(order['total_amount'])}

DELIVERY ADDRESS
================
{order['customer_name']}
{order['delivery_address']}
{order['delivery_city']}, {order['delivery_province']} {order['delivery_postcode']}

We will be in touch shortly to confirm your order and provide delivery details.

Thank you for choosing {STORE_NAME}!

---
{STORE_NAME}
Authorized EBC Brakes Reseller · South Africa
        """.strip()

        # Create the email message object
        msg            = MIMEText(body)
        msg['Subject'] = f"Order Confirmation — {order['order_number']}"
        msg['From']    = EMAIL_FROM
        msg['To']      = order['customer_email']

        # Connect to the email server and send
        # During development this goes to the smtpd debugging server
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.sendmail(EMAIL_FROM, [order['customer_email']], msg.as_string())

        print(f"📧 Email sent to {order['customer_email']}")

    except Exception as e:
        # If email fails, just log it - don't crash the order
        print(f"⚠️  Email could not be sent: {e}")
        print("   (This is normal if the smtpd debugging server is not running)")


# ==============================================================================
# JINJA2 CUSTOM FILTERS
# These let us use format_currency directly in our HTML templates
# e.g. {{ 1250.00 | currency }}
# ==============================================================================

@app.template_filter('currency')
def currency_filter(amount):
    return format_currency(amount)


# ==============================================================================
# WEBSITE PAGE ROUTES
# ==============================================================================

@app.route('/')
def home():
    """Home page with vehicle finder."""
    return render_template('index.html')


@app.route('/results')
def results():
    """
    Results page - shows all parts that fit a searched vehicle.
    URL example: /results?make=Toyota&model=Corolla&year=2018
    """
    make   = request.args.get('make',   '').strip()
    model  = request.args.get('model',  '').strip()
    year   = request.args.get('year',   '').strip()
    engine = request.args.get('engine', '').strip()

    if not make:
        return render_template('index.html')

    conn = get_db_connection()

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
            v.engine
        FROM vehicle_fitment vf
        JOIN vehicles v ON vf.vehicle_id  = v.id
        JOIN products  p ON vf.part_number = p.part_number
        WHERE v.make  = ?
          AND v.model = ?
    '''
    params = [make, model]

    if year:
        sql += ' AND v.year = ?'
        params.append(year)
    if engine:
        sql += ' AND v.engine = ?'
        params.append(engine)

    sql += ' ORDER BY p.category, vf.position'

    parts      = conn.execute(sql, params).fetchall()
    conn.close()

    parts_list = [dict(row) for row in parts]

    # Group parts by category for display
    grouped = {}
    for part in parts_list:
        cat = part['category'] or 'Other'
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append(part)

    # Pass current cart count to show in nav
    cart_count = sum(
        item['quantity'] for item in session.get('cart', {}).values()
    )

    return render_template('results.html',
        grouped_parts = grouped,
        make          = make,
        model         = model,
        year          = year,
        engine        = engine,
        total_results = len(parts_list),
        cart_count    = cart_count
    )


@app.route('/cart')
def cart_page():
    """
    The shopping cart page.
    Shows all items the customer has added, with quantities and totals.
    """
    cart  = session.get('cart', {})
    items = list(cart.values())

    # Calculate totals
    # In SA, VAT is 15%
    # srp_incl_vat already includes VAT so we work backwards
    subtotal   = sum(item['unit_price'] * item['quantity'] for item in items)
    # VAT portion = total - (total / 1.15)
    vat_amount = round(subtotal - (subtotal / 1.15), 2)
    # For now delivery is free - we'll add delivery calculation later
    delivery   = 0.00
    total      = round(subtotal + delivery, 2)

    return render_template('cart.html',
        items      = items,
        subtotal   = subtotal,
        vat_amount = vat_amount,
        delivery   = delivery,
        total      = total,
        cart_count = len(items)
    )


@app.route('/checkout')
def checkout_page():
    """
    The checkout page.
    Customer fills in their delivery details here.
    """
    cart = session.get('cart', {})

    # If cart is empty, send them back to home
    if not cart:
        return render_template('index.html')

    items      = list(cart.values())
    subtotal   = sum(item['unit_price'] * item['quantity'] for item in items)
    vat_amount = round(subtotal - (subtotal / 1.15), 2)
    delivery   = 0.00
    total      = round(subtotal + delivery, 2)

    return render_template('checkout.html',
        items      = items,
        subtotal   = subtotal,
        vat_amount = vat_amount,
        delivery   = delivery,
        total      = total,
        cart_count = len(items)
    )


@app.route('/order/confirmation/<order_number>')
def order_confirmation(order_number):
    """
    Order confirmation page shown after a successful checkout.
    """
    conn  = get_db_connection()
    order = conn.execute(
        'SELECT * FROM orders WHERE order_number = ?', (order_number,)
    ).fetchone()

    if order is None:
        conn.close()
        return render_template('index.html')

    items = conn.execute(
        'SELECT * FROM order_items WHERE order_id = ?', (order['id'],)
    ).fetchall()

    conn.close()

    return render_template('order_confirmation.html',
        order = dict(order),
        items = [dict(i) for i in items]
    )


# ==============================================================================
# API ROUTES — CART
# The cart lives in the Flask session (a cookie on the customer's browser).
# Each item in the cart is stored as a dictionary keyed by part_number.
# ==============================================================================

@app.route('/api/cart', methods=['GET'])
def get_cart():
    """
    GET /api/cart
    Returns the current contents of the cart.
    """
    cart  = session.get('cart', {})
    items = list(cart.values())
    total = sum(item['unit_price'] * item['quantity'] for item in items)
    return jsonify({
        'items'      : items,
        'item_count' : len(items),
        'total'      : round(total, 2)
    }), 200


@app.route('/api/cart/add', methods=['POST'])
def add_to_cart():
    """
    POST /api/cart/add
    Adds a product to the cart, or increases its quantity if already there.

    Expected JSON:
    {
        "part_number"  : "DP21074",
        "product_type" : "EBC Greenstuff Front Pads",
        "unit_price"   : 850.00,
        "quantity"     : 1
    }
    """
    data = request.get_json()

    # Validate required fields
    required = ['part_number', 'product_type', 'unit_price']
    for field in required:
        if field not in data:
            return jsonify({'error': f'Missing field: {field}'}), 400

    part_number  = data['part_number']
    product_type = data['product_type']
    unit_price   = float(data['unit_price'])
    quantity     = int(data.get('quantity', 1))

    # Get the cart from session, or start a new empty one
    cart = session.get('cart', {})

    if part_number in cart:
        # Already in cart - just increase the quantity
        cart[part_number]['quantity'] += quantity
    else:
        # New item - add it
        cart[part_number] = {
            'part_number' : part_number,
            'product_type': product_type,
            'unit_price'  : unit_price,
            'quantity'    : quantity,
            'line_total'  : round(unit_price * quantity, 2)
        }

    # Recalculate line total
    cart[part_number]['line_total'] = round(
        cart[part_number]['unit_price'] * cart[part_number]['quantity'], 2
    )

    # Save the updated cart back to the session
    session['cart']    = cart
    session.modified   = True  # Tell Flask the session has changed

    cart_count = sum(item['quantity'] for item in cart.values())

    return jsonify({
        'message'    : f'{part_number} added to cart!',
        'cart_count' : cart_count
    }), 200


@app.route('/api/cart/update', methods=['PATCH'])
def update_cart():
    """
    PATCH /api/cart/update
    Updates the quantity of an item already in the cart.

    Expected JSON:
    {
        "part_number" : "DP21074",
        "quantity"    : 2
    }
    """
    data        = request.get_json()
    part_number = data.get('part_number')
    quantity    = int(data.get('quantity', 1))

    cart = session.get('cart', {})

    if part_number not in cart:
        return jsonify({'error': 'Item not found in cart'}), 404

    if quantity <= 0:
        # If quantity is set to 0 or less, remove the item
        del cart[part_number]
    else:
        cart[part_number]['quantity']   = quantity
        cart[part_number]['line_total'] = round(
            cart[part_number]['unit_price'] * quantity, 2
        )

    session['cart']  = cart
    session.modified = True

    return jsonify({'message': 'Cart updated!'}), 200


@app.route('/api/cart/remove/<part_number>', methods=['DELETE'])
def remove_from_cart(part_number):
    """
    DELETE /api/cart/remove/DP21074
    Removes a single item from the cart completely.
    """
    cart = session.get('cart', {})

    if part_number not in cart:
        return jsonify({'error': 'Item not in cart'}), 404

    del cart[part_number]
    session['cart']  = cart
    session.modified = True

    return jsonify({'message': f'{part_number} removed from cart'}), 200


@app.route('/api/cart/clear', methods=['DELETE'])
def clear_cart():
    """
    DELETE /api/cart/clear
    Empties the entire cart.
    Called after a successful order is placed.
    """
    session.pop('cart', None)
    return jsonify({'message': 'Cart cleared'}), 200


# ==============================================================================
# API ROUTES — ORDERS
# ==============================================================================

@app.route('/api/orders', methods=['POST'])
def create_order():
    """
    POST /api/orders
    Creates a new order from the current cart + customer details.

    Expected JSON (customer details from checkout form):
    {
        "customer_name"     : "John Smith",
        "customer_email"    : "john@example.com",
        "customer_phone"    : "082 000 0000",
        "delivery_address"  : "123 Main Road",
        "delivery_city"     : "Cape Town",
        "delivery_province" : "Western Cape",
        "delivery_postcode" : "8001",
        "order_notes"       : "Please call before delivery"
    }
    """
    data = request.get_json()
    cart = session.get('cart', {})

    # Can't place an order with an empty cart
    if not cart:
        return jsonify({'error': 'Your cart is empty'}), 400

    # Validate required customer fields
    required = [
        'customer_name', 'customer_email',
        'delivery_address', 'delivery_city',
        'delivery_province', 'delivery_postcode'
    ]
    for field in required:
        if not data.get(field, '').strip():
            return jsonify({'error': f'Missing required field: {field}'}), 400

    # Calculate order totals
    items      = list(cart.values())
    subtotal   = sum(item['unit_price'] * item['quantity'] for item in items)
    subtotal   = round(subtotal, 2)
    vat_amount = round(subtotal - (subtotal / 1.15), 2)
    delivery   = 0.00
    total      = round(subtotal + delivery, 2)

    # Generate a unique order number
    order_number = generate_order_number()

    conn = get_db_connection()
    try:
        # Insert the order record
        cursor = conn.execute('''
            INSERT INTO orders (
                order_number, customer_name, customer_email, customer_phone,
                delivery_address, delivery_city, delivery_province,
                delivery_postcode, order_notes,
                subtotal, vat_amount, delivery_fee, total_amount
            ) VALUES (
                :order_number, :customer_name, :customer_email, :customer_phone,
                :delivery_address, :delivery_city, :delivery_province,
                :delivery_postcode, :order_notes,
                :subtotal, :vat_amount, :delivery_fee, :total_amount
            )
        ''', {
            'order_number'    : order_number,
            'customer_name'   : data['customer_name'].strip(),
            'customer_email'  : data['customer_email'].strip(),
            'customer_phone'  : data.get('customer_phone', '').strip(),
            'delivery_address': data['delivery_address'].strip(),
            'delivery_city'   : data['delivery_city'].strip(),
            'delivery_province': data['delivery_province'].strip(),
            'delivery_postcode': data['delivery_postcode'].strip(),
            'order_notes'     : data.get('order_notes', '').strip(),
            'subtotal'        : subtotal,
            'vat_amount'      : vat_amount,
            'delivery_fee'    : delivery,
            'total_amount'    : total
        })

        order_id = cursor.lastrowid

        # Insert each cart item as an order line
        for item in items:
            line_total = round(item['unit_price'] * item['quantity'], 2)

            # Look up the category for this part
            product = conn.execute(
                'SELECT category FROM products WHERE part_number = ?',
                (item['part_number'],)
            ).fetchone()
            category = product['category'] if product else 'Unknown'

            conn.execute('''
                INSERT INTO order_items
                    (order_id, part_number, product_type, category,
                     quantity, unit_price, line_total)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                order_id,
                item['part_number'],
                item['product_type'],
                category,
                item['quantity'],
                item['unit_price'],
                line_total
            ))

        conn.commit()

        # Get the full order back so we can send the email
        order = dict(conn.execute(
            'SELECT * FROM orders WHERE id = ?', (order_id,)
        ).fetchone())

        conn.close()

        # Send confirmation email (goes to smtpd debug server locally)
        send_order_email(order, items)

        # Clear the cart now that the order is placed
        session.pop('cart', None)

        print(f"✅ Order {order_number} created successfully!")

        return jsonify({
            'message'      : 'Order placed successfully!',
            'order_number' : order_number
        }), 201

    except Exception as e:
        conn.close()
        print(f"❌ Order creation failed: {e}")
        return jsonify({'error': 'Order could not be created. Please try again.'}), 500


@app.route('/api/orders', methods=['GET'])
def get_all_orders():
    """
    GET /api/orders
    Returns all orders. For admin use.
    """
    conn   = get_db_connection()
    orders = conn.execute(
        'SELECT * FROM orders ORDER BY created_at DESC'
    ).fetchall()
    conn.close()
    return jsonify([dict(row) for row in orders]), 200


@app.route('/api/orders/<order_number>', methods=['GET'])
def get_order(order_number):
    """
    GET /api/orders/EBC-20250413-0001
    Returns a single order with all its items.
    """
    conn  = get_db_connection()
    order = conn.execute(
        'SELECT * FROM orders WHERE order_number = ?', (order_number,)
    ).fetchone()

    if order is None:
        conn.close()
        return jsonify({'error': 'Order not found'}), 404

    items = conn.execute(
        'SELECT * FROM order_items WHERE order_id = ?', (order['id'],)
    ).fetchall()

    conn.close()

    result          = dict(order)
    result['items'] = [dict(i) for i in items]
    return jsonify(result), 200


# ==============================================================================
# API ROUTES — VEHICLE FINDER DROPDOWNS
# ==============================================================================

@app.route('/api/makes', methods=['GET'])
def get_makes():
    conn  = get_db_connection()
    rows  = conn.execute(
        'SELECT DISTINCT make FROM vehicles WHERE make IS NOT NULL ORDER BY make'
    ).fetchall()
    conn.close()
    return jsonify([row['make'] for row in rows]), 200


@app.route('/api/models', methods=['GET'])
def get_models():
    make = request.args.get('make', '').strip()
    if not make:
        return jsonify({'error': 'make is required'}), 400
    conn = get_db_connection()
    rows = conn.execute(
        'SELECT DISTINCT model FROM vehicles WHERE make = ? AND model IS NOT NULL ORDER BY model',
        (make,)
    ).fetchall()
    conn.close()
    return jsonify([row['model'] for row in rows]), 200


@app.route('/api/years', methods=['GET'])
def get_years():
    make  = request.args.get('make',  '').strip()
    model = request.args.get('model', '').strip()
    if not make or not model:
        return jsonify({'error': 'make and model are required'}), 400
    conn = get_db_connection()
    rows = conn.execute(
        'SELECT DISTINCT year FROM vehicles WHERE make=? AND model=? AND year IS NOT NULL ORDER BY year',
        (make, model)
    ).fetchall()
    conn.close()
    return jsonify([row['year'] for row in rows]), 200


@app.route('/api/engines', methods=['GET'])
def get_engines():
    make  = request.args.get('make',  '').strip()
    model = request.args.get('model', '').strip()
    year  = request.args.get('year',  '').strip()
    if not make or not model:
        return jsonify({'error': 'make and model are required'}), 400
    conn = get_db_connection()
    if year:
        rows = conn.execute(
            'SELECT DISTINCT engine FROM vehicles WHERE make=? AND model=? AND year=? AND engine IS NOT NULL ORDER BY engine',
            (make, model, year)
        ).fetchall()
    else:
        rows = conn.execute(
            'SELECT DISTINCT engine FROM vehicles WHERE make=? AND model=? AND engine IS NOT NULL ORDER BY engine',
            (make, model)
        ).fetchall()
    conn.close()
    return jsonify([row['engine'] for row in rows]), 200


@app.route('/api/categories', methods=['GET'])
def get_categories():
    conn = get_db_connection()
    rows = conn.execute(
        'SELECT category, COUNT(*) as count FROM products WHERE category IS NOT NULL GROUP BY category ORDER BY count DESC'
    ).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows]), 200


# ==============================================================================
# API ROUTES — PRODUCTS
# ==============================================================================

@app.route('/api/products', methods=['GET'])
def get_all_products():
    category = request.args.get('category', '').strip()
    conn     = get_db_connection()
    if category:
        products = conn.execute(
            'SELECT * FROM products WHERE category = ? ORDER BY part_number', (category,)
        ).fetchall()
    else:
        products = conn.execute(
            'SELECT * FROM products ORDER BY part_number'
        ).fetchall()
    conn.close()
    return jsonify([dict(row) for row in products]), 200


@app.route('/api/products/<part_number>', methods=['GET'])
def get_product(part_number):
    conn    = get_db_connection()
    product = conn.execute(
        'SELECT * FROM products WHERE part_number = ?', (part_number,)
    ).fetchone()
    if product is None:
        conn.close()
        return jsonify({'error': f'Product {part_number} not found'}), 404
    fitments = conn.execute(
        '''SELECT v.make, v.model, v.sub_model, v.year, v.engine, vf.position
           FROM vehicle_fitment vf
           JOIN vehicles v ON vf.vehicle_id = v.id
           WHERE vf.part_number = ?
           ORDER BY v.make, v.model, v.year''',
        (part_number,)
    ).fetchall()
    conn.close()
    result           = dict(product)
    result['fits']   = [dict(row) for row in fitments]
    return jsonify(result), 200


@app.route('/api/products/<part_number>', methods=['PATCH'])
def update_product(part_number):
    conn     = get_db_connection()
    existing = conn.execute(
        'SELECT * FROM products WHERE part_number = ?', (part_number,)
    ).fetchone()
    if existing is None:
        conn.close()
        return jsonify({'error': f'Product {part_number} not found'}), 404
    data    = request.get_json()
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
    conn     = get_db_connection()
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
        print(f"🚀 Starting {STORE_NAME} server...")
        print("🌐 Store    : http://localhost:5000")
        print("🛒 Cart     : http://localhost:5000/cart")
        print("📦 API      : http://localhost:5000/api/products")
        print("⛔ Stop     : CTRL + C\n")

    app.run(debug=True, port=5000)