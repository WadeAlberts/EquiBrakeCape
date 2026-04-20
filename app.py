# =============================================================================
# app.py
# =============================================================================
# Main server - runs the website and all API endpoints.
# Start: python3 app.py
# Stop:  CTRL + C
#
# PHASE 5 FIX:
#   /payfast/notify correctly passes raw_body + received_signature
#   to verify_itn_signature() instead of the old post_data dict
#
# UI/UX UPDATE:
#   /results now handles three search modes:
#     1. Vehicle search  — ?make=Toyota&model=Corolla&year=2018&engine=1.8
#     2. Part number     — ?part_number=DP21232   (new — from part number search box)
#     3. Category browse — ?category=Brake+Pads   (new — from clicking a category card)
# =============================================================================

from flask import Flask, request, jsonify, render_template, session, redirect
import sqlite3
import os
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
from dotenv import load_dotenv
from payfast_helper import (
    build_payfast_form_data,
    verify_itn_signature
)

load_dotenv()

# ------------------------------------------------------------------------------
# APP SETUP
# ------------------------------------------------------------------------------

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'equibrakecape-dev-secret-key-2025')

DATABASE = 'products.db'
BASE_URL  = os.environ.get('BASE_URL', 'http://localhost:5000').rstrip('/')

# ------------------------------------------------------------------------------
# EMAIL CONFIGURATION
# Open a second terminal and run:
#   python3 -m smtpd -n -c DebuggingServer localhost:1025
# Emails print there during development instead of being sent for real.
# ------------------------------------------------------------------------------
EMAIL_HOST  = 'localhost'
EMAIL_PORT  = 1025
EMAIL_FROM  = 'orders@equibrakecape.co.za'
STORE_NAME  = 'Equi Brake Cape'


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
    e.g. 1250.50 → R1 250.50
    """
    if amount is None:
        return 'R0.00'
    formatted = f"{amount:,.2f}".replace(',', ' ')
    return f"R{formatted}"


def generate_order_number():
    """Generates a unique order number e.g. EBC-20260419-0001"""
    today = datetime.now().strftime('%Y%m%d')
    conn  = get_db_connection()
    count = conn.execute(
        "SELECT COUNT(*) as c FROM orders WHERE order_number LIKE ?",
        (f'EBC-{today}-%',)
    ).fetchone()['c']
    conn.close()
    return f"EBC-{today}-{str(count + 1).zfill(4)}"


def send_order_email(order, items):
    """
    Sends a payment confirmation email to the customer.
    Called from /payfast/notify AFTER PayFast confirms payment.
    During development this prints to the smtpd debug terminal.
    """
    try:
        items_text = "\n".join([
            f"  {item['part_number']} x{item['quantity']} — {format_currency(item['line_total'])}"
            for item in items
        ])

        body = f"""
Dear {order['customer_name']},

Great news — your payment has been confirmed and your order is being processed!

ORDER DETAILS
=============
Order Number : {order['order_number']}
Date         : {order['created_at']}
Status       : Payment Confirmed ✅

ITEMS ORDERED
=============
{items_text}

ORDER TOTAL
===========
Subtotal     : {format_currency(order['subtotal'])}
VAT (15%)    : {format_currency(order['vat_amount'])}
Delivery     : {format_currency(order['delivery_fee'])}
TOTAL PAID   : {format_currency(order['total_amount'])}

DELIVERY ADDRESS
================
{order['customer_name']}
{order['delivery_address']}
{order['delivery_city']}, {order['delivery_province']} {order['delivery_postcode']}

We will be in touch shortly with your delivery details.

Thank you for choosing {STORE_NAME}!

---
{STORE_NAME}
Authorized EBC Brakes Reseller · South Africa
        """.strip()

        msg            = MIMEText(body)
        msg['Subject'] = f"Payment Confirmed — {order['order_number']}"
        msg['From']    = EMAIL_FROM
        msg['To']      = order['customer_email']

        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.sendmail(EMAIL_FROM, [order['customer_email']], msg.as_string())

        print(f"📧 Confirmation email sent to {order['customer_email']}")

    except Exception as e:
        print(f"⚠️  Email could not be sent: {e}")
        print("   (Normal if smtpd debug server is not running)")


# ==============================================================================
# JINJA2 CUSTOM FILTERS
# Lets us use {{ 1250.00 | currency }} in HTML templates
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
    Results page — shows matching parts based on how the customer searched.

    There are now THREE ways to reach this page:

    MODE 1 — Vehicle search (original):
        URL: /results?make=Toyota&model=Corolla&year=2018&engine=1.8
        How: Customer used the vehicle finder dropdowns
        SQL: Joins vehicle_fitment → vehicles → products

    MODE 2 — Part number search (new):
        URL: /results?part_number=DP21232
        How: Customer typed a part number into the search box
        SQL: Searches the products table directly by part_number
             Uses LIKE so partial matches work (e.g. "DP212" finds "DP21232")

    MODE 3 — Category browse (new):
        URL: /results?category=Brake+Pads
        How: Customer clicked a category card on the home page
        SQL: Returns all products in that category from the products table
    """

    # -----------------------------------------------------------------------
    # Read all possible URL parameters
    # .strip() removes any accidental spaces the browser might add
    # -----------------------------------------------------------------------
    make        = request.args.get('make',        '').strip()
    model       = request.args.get('model',       '').strip()
    year        = request.args.get('year',        '').strip()
    engine      = request.args.get('engine',      '').strip()
    part_number = request.args.get('part_number', '').strip()
    category    = request.args.get('category',    '').strip()

    conn = get_db_connection()

    # -----------------------------------------------------------------------
    # MODE 2: Part number search
    # Triggered when ?part_number= is in the URL
    # -----------------------------------------------------------------------
    if part_number:

        print(f"🔍 Part number search: '{part_number}'")

        # Use LIKE with % wildcards so partial matches work.
        # e.g. searching "DP212" will find "DP21232", "DP21274" etc.
        # The UPPER() function makes the search case-insensitive
        # so "dp21232" finds "DP21232"
        search_term = f"%{part_number.upper()}%"

        rows = conn.execute(
            '''
            SELECT part_number, category, srp_incl_vat, srp_excl_vat
            FROM products
            WHERE UPPER(part_number) LIKE ?
            ORDER BY part_number
            ''',
            (search_term,)
        ).fetchall()

        conn.close()

        # Convert database rows into plain Python dicts
        parts_list = [dict(row) for row in rows]

        # Group parts by category (same format as vehicle search results)
        # This means results.html works exactly the same for all 3 modes
        grouped = {}
        for part in parts_list:
            cat = part['category'] or 'Other'
            if cat not in grouped:
                grouped[cat] = []
            grouped[cat].append(part)

        cart_count = sum(item['quantity'] for item in session.get('cart', {}).values())

        # Pass search_mode so results.html can show the right heading
        return render_template('results.html',
            grouped_parts  = grouped,
            total_results  = len(parts_list),
            cart_count     = cart_count,
            search_mode    = 'part_number',   # Tells template which heading to show
            part_number    = part_number,      # Used in the results heading e.g. "Results for DP21232"
            # Vehicle fields are empty for this mode
            make           = '',
            model          = '',
            year           = '',
            engine         = '',
            category       = ''
        )

    # -----------------------------------------------------------------------
    # MODE 3: Category browse
    # Triggered when ?category= is in the URL (from clicking a category card)
    # -----------------------------------------------------------------------
    elif category:

        print(f"🔍 Category browse: '{category}'")

        rows = conn.execute(
            '''
            SELECT part_number, category, srp_incl_vat, srp_excl_vat
            FROM products
            WHERE category = ?
            ORDER BY part_number
            ''',
            (category,)
        ).fetchall()

        conn.close()

        parts_list = [dict(row) for row in rows]

        # All parts in a category browse have the same category,
        # so the grouped dict will have just one key.
        grouped = {}
        for part in parts_list:
            cat = part['category'] or 'Other'
            if cat not in grouped:
                grouped[cat] = []
            grouped[cat].append(part)

        cart_count = sum(item['quantity'] for item in session.get('cart', {}).values())

        return render_template('results.html',
            grouped_parts  = grouped,
            total_results  = len(parts_list),
            cart_count     = cart_count,
            search_mode    = 'category',      # Tells template which heading to show
            category       = category,         # Used in the heading e.g. "Brake Pads"
            # Vehicle fields are empty for this mode
            make           = '',
            model          = '',
            year           = '',
            engine         = '',
            part_number    = ''
        )

    # -----------------------------------------------------------------------
    # MODE 1: Vehicle search (original behaviour — unchanged)
    # Triggered when ?make= and ?model= are in the URL
    # -----------------------------------------------------------------------
    elif make and model:

        print(f"🔍 Vehicle search: {make} {model} {year} {engine}")

        sql = '''
            SELECT DISTINCT
                p.part_number, p.category, p.srp_incl_vat, p.srp_excl_vat,
                vf.product_type, vf.position,
                v.make, v.model, v.sub_model, v.year, v.engine
            FROM vehicle_fitment vf
            JOIN vehicles v ON vf.vehicle_id  = v.id
            JOIN products  p ON vf.part_number = p.part_number
            WHERE v.make = ? AND v.model = ?
        '''
        params = [make, model]

        # Year and engine are optional — only filter if provided
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

        cart_count = sum(item['quantity'] for item in session.get('cart', {}).values())

        return render_template('results.html',
            grouped_parts  = grouped,
            make           = make,
            model          = model,
            year           = year,
            engine         = engine,
            total_results  = len(parts_list),
            cart_count     = cart_count,
            search_mode    = 'vehicle',       # Tells template which heading to show
            part_number    = '',
            category       = ''
        )

    # -----------------------------------------------------------------------
    # FALLBACK: No valid search parameters — send back to home page
    # -----------------------------------------------------------------------
    else:
        conn.close()
        print("⚠️  /results called with no valid search parameters — redirecting home")
        return redirect('/')


@app.route('/cart')
def cart_page():
    """Shopping cart page."""
    cart  = session.get('cart', {})
    items = list(cart.values())

    subtotal   = sum(item['unit_price'] * item['quantity'] for item in items)
    vat_amount = round(subtotal - (subtotal / 1.15), 2)
    delivery   = 0.00
    total      = round(subtotal + delivery, 2)

    return render_template('cart.html',
        items=items, subtotal=subtotal, vat_amount=vat_amount,
        delivery=delivery, total=total, cart_count=len(items)
    )


@app.route('/checkout')
def checkout_page():
    """Checkout page — customer fills in delivery details."""
    cart = session.get('cart', {})
    if not cart:
        return render_template('index.html')

    items      = list(cart.values())
    subtotal   = sum(item['unit_price'] * item['quantity'] for item in items)
    vat_amount = round(subtotal - (subtotal / 1.15), 2)
    delivery   = 0.00
    total      = round(subtotal + delivery, 2)

    return render_template('checkout.html',
        items=items, subtotal=subtotal, vat_amount=vat_amount,
        delivery=delivery, total=total, cart_count=len(items)
    )


@app.route('/order/confirmation/<order_number>')
def order_confirmation(order_number):
    """
    Confirmation page — shown after PayFast redirects the customer back.
    payment_status in the database drives what the page displays.
    """
    conn  = get_db_connection()
    order = conn.execute(
        'SELECT * FROM orders WHERE order_number = ?', (order_number,)
    ).fetchone()

    if order is None:
        conn.close()
        return redirect('/')

    items = conn.execute(
        'SELECT * FROM order_items WHERE order_id = ?', (order['id'],)
    ).fetchall()
    conn.close()

    return render_template('order_confirmation.html',
        order = dict(order),
        items = [dict(i) for i in items]
    )


# ==============================================================================
# PAYFAST PAYMENT ROUTES
# ==============================================================================

@app.route('/payfast/notify', methods=['POST'])
def payfast_notify():
    """
    POST /payfast/notify
    ====================
    PayFast secretly calls this URL after a payment completes (ITN).

    KEY FIX: We read the raw POST body as a plain string using
    request.get_data(as_text=True) BEFORE Flask parses it.
    We then pass that raw string into verify_itn_signature() so we
    hash exactly the same bytes that PayFast hashed — guaranteeing a match.

    We still use request.form to conveniently READ individual field values.
    """

    # ------------------------------------------------------------------
    # Read the raw POST body exactly as PayFast sent it.
    # This is a plain string like:
    # "m_payment_id=EBC-...&pf_payment_id=123&payment_status=COMPLETE&...&signature=abc"
    # ------------------------------------------------------------------
    raw_body  = request.get_data(as_text=True)

    # Also parse the form fields for easy value reading
    post_data = request.form.to_dict()

    # Pull out the individual values we need
    received_signature = post_data.get('signature', '')
    payment_status     = post_data.get('payment_status', '').upper()
    order_number       = post_data.get('m_payment_id', '')
    pf_payment_id      = post_data.get('pf_payment_id', '')
    amount_gross       = post_data.get('amount_gross', '0')

    print(f"📬 PayFast ITN received | Status: {payment_status} | Order: {order_number}")

    # ------------------------------------------------------------------
    # STEP 1: Verify the signature using the RAW body string.
    # ------------------------------------------------------------------
    passphrase = os.environ.get('PAYFAST_PASSPHRASE', '')

    if not verify_itn_signature(raw_body, received_signature, passphrase):
        print("❌ ITN signature check failed — ignoring this notification")
        return 'OK', 200   # Return 200 so PayFast stops retrying

    # ------------------------------------------------------------------
    # STEP 2: Check we have an order number to work with
    # ------------------------------------------------------------------
    if not order_number:
        print("⚠️  ITN: No m_payment_id found in notification")
        return 'OK', 200

    conn  = get_db_connection()
    order = conn.execute(
        'SELECT * FROM orders WHERE order_number = ?', (order_number,)
    ).fetchone()

    if not order:
        print(f"⚠️  ITN: No order found for: {order_number}")
        conn.close()
        return 'OK', 200

    # ------------------------------------------------------------------
    # STEP 3: Verify the amount matches what we stored
    # Prevents someone paying R1 for a R1,250 order
    # ------------------------------------------------------------------
    try:
        received_amount = float(amount_gross)
        expected_amount = float(order['total_amount'])
        if abs(received_amount - expected_amount) > 0.01:
            print(f"❌ Amount mismatch! Expected R{expected_amount:.2f}, got R{received_amount:.2f}")
            conn.close()
            return 'OK', 200
    except ValueError:
        print(f"⚠️  Could not parse amount: {amount_gross}")

    # ------------------------------------------------------------------
    # STEP 4: Update the order based on PayFast's payment_status
    # ------------------------------------------------------------------
    if payment_status == 'COMPLETE':

        conn.execute('''
            UPDATE orders
            SET payment_status     = 'paid',
                status             = 'confirmed',
                payfast_payment_id = ?
            WHERE order_number = ?
        ''', (pf_payment_id, order_number))
        conn.commit()

        items = conn.execute(
            'SELECT * FROM order_items WHERE order_id = ?', (order['id'],)
        ).fetchall()

        order_dict                   = dict(order)
        order_dict['payment_status'] = 'paid'
        order_dict['status']         = 'confirmed'

        print(f"✅ Payment CONFIRMED for {order_number} | PayFast ID: {pf_payment_id}")

        send_order_email(order_dict, [dict(i) for i in items])

    elif payment_status == 'FAILED':
        conn.execute('''
            UPDATE orders SET payment_status = 'failed', status = 'cancelled'
            WHERE order_number = ?
        ''', (order_number,))
        conn.commit()
        print(f"❌ Payment FAILED for {order_number}")

    elif payment_status == 'PENDING':
        conn.execute('''
            UPDATE orders SET payment_status = 'pending_payment'
            WHERE order_number = ?
        ''', (order_number,))
        conn.commit()
        print(f"⏳ Payment PENDING (EFT) for {order_number}")

    conn.close()
    return 'OK', 200


@app.route('/payment/cancelled/<order_number>')
def payment_cancelled(order_number):
    """
    PayFast sends the customer here if they click Cancel on the payment page.
    We update the order and show the confirmation page with a cancelled message.
    """
    conn = get_db_connection()
    conn.execute('''
        UPDATE orders SET payment_status = 'cancelled', status = 'cancelled'
        WHERE order_number = ?
    ''', (order_number,))
    conn.commit()

    order = conn.execute(
        'SELECT * FROM orders WHERE order_number = ?', (order_number,)
    ).fetchone()
    items = []
    if order:
        items = conn.execute(
            'SELECT * FROM order_items WHERE order_id = ?', (order['id'],)
        ).fetchall()
    conn.close()

    if not order:
        return redirect('/')

    print(f"❌ Payment cancelled for order {order_number}")
    return render_template('order_confirmation.html',
        order = dict(order),
        items = [dict(i) for i in items]
    )


# ==============================================================================
# API ROUTES — CART
# ==============================================================================

@app.route('/api/cart', methods=['GET'])
def get_cart():
    """GET /api/cart — Returns the current cart contents."""
    cart  = session.get('cart', {})
    items = list(cart.values())
    total = sum(item['unit_price'] * item['quantity'] for item in items)
    return jsonify({'items': items, 'item_count': len(items), 'total': round(total, 2)}), 200


@app.route('/api/cart/add', methods=['POST'])
def add_to_cart():
    """POST /api/cart/add — Adds an item to the cart."""
    data = request.get_json()

    for field in ['part_number', 'product_type', 'unit_price']:
        if field not in data:
            return jsonify({'error': f'Missing field: {field}'}), 400

    part_number = data['part_number']
    unit_price  = float(data['unit_price'])
    quantity    = int(data.get('quantity', 1))
    cart        = session.get('cart', {})

    if part_number in cart:
        cart[part_number]['quantity'] += quantity
    else:
        cart[part_number] = {
            'part_number' : part_number,
            'product_type': data['product_type'],
            'unit_price'  : unit_price,
            'quantity'    : quantity,
            'line_total'  : round(unit_price * quantity, 2)
        }

    cart[part_number]['line_total'] = round(
        cart[part_number]['unit_price'] * cart[part_number]['quantity'], 2
    )
    session['cart']  = cart
    session.modified = True

    return jsonify({
        'message'    : f"{part_number} added to cart!",
        'cart_count' : sum(item['quantity'] for item in cart.values())
    }), 200


@app.route('/api/cart/update', methods=['PATCH'])
def update_cart():
    """PATCH /api/cart/update — Updates the quantity of a cart item."""
    data        = request.get_json()
    part_number = data.get('part_number')
    quantity    = int(data.get('quantity', 1))
    cart        = session.get('cart', {})

    if part_number not in cart:
        return jsonify({'error': 'Item not found in cart'}), 404

    if quantity <= 0:
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
    """DELETE /api/cart/remove/DP21074 — Removes one item from the cart."""
    cart = session.get('cart', {})
    if part_number not in cart:
        return jsonify({'error': 'Item not in cart'}), 404
    del cart[part_number]
    session['cart']  = cart
    session.modified = True
    return jsonify({'message': f'{part_number} removed from cart'}), 200


@app.route('/api/cart/clear', methods=['DELETE'])
def clear_cart():
    """DELETE /api/cart/clear — Empties the entire cart."""
    session.pop('cart', None)
    return jsonify({'message': 'Cart cleared'}), 200


# ==============================================================================
# API ROUTES — ORDERS
# ==============================================================================

@app.route('/api/orders', methods=['POST'])
def create_order():
    """
    POST /api/orders
    ================
    1. Validates the checkout form fields
    2. Saves the order to the database (payment_status = 'pending_payment')
    3. Builds the PayFast form data + signature
    4. Returns the PayFast URL + form fields to the browser
    5. Browser JS builds a hidden form and submits it to PayFast
    """
    data = request.get_json()
    cart = session.get('cart', {})

    if not cart:
        return jsonify({'error': 'Your cart is empty'}), 400

    required = [
        'customer_name', 'customer_email',
        'delivery_address', 'delivery_city',
        'delivery_province', 'delivery_postcode'
    ]
    for field in required:
        if not data.get(field, '').strip():
            return jsonify({'error': f'Missing required field: {field}'}), 400

    items      = list(cart.values())
    subtotal   = round(sum(item['unit_price'] * item['quantity'] for item in items), 2)
    vat_amount = round(subtotal - (subtotal / 1.15), 2)
    delivery   = 0.00
    total      = round(subtotal + delivery, 2)

    order_number = generate_order_number()

    conn = get_db_connection()
    try:
        cursor = conn.execute('''
            INSERT INTO orders (
                order_number, status, payment_status,
                customer_name, customer_email, customer_phone,
                delivery_address, delivery_city, delivery_province,
                delivery_postcode, order_notes,
                subtotal, vat_amount, delivery_fee, total_amount
            ) VALUES (
                :order_number, 'pending', 'pending_payment',
                :customer_name, :customer_email, :customer_phone,
                :delivery_address, :delivery_city, :delivery_province,
                :delivery_postcode, :order_notes,
                :subtotal, :vat_amount, :delivery_fee, :total_amount
            )
        ''', {
            'order_number'     : order_number,
            'customer_name'    : data['customer_name'].strip(),
            'customer_email'   : data['customer_email'].strip(),
            'customer_phone'   : data.get('customer_phone', '').strip(),
            'delivery_address' : data['delivery_address'].strip(),
            'delivery_city'    : data['delivery_city'].strip(),
            'delivery_province': data['delivery_province'].strip(),
            'delivery_postcode': data['delivery_postcode'].strip(),
            'order_notes'      : data.get('order_notes', '').strip(),
            'subtotal'         : subtotal,
            'vat_amount'       : vat_amount,
            'delivery_fee'     : delivery,
            'total_amount'     : total
        })

        order_id = cursor.lastrowid

        for item in items:
            line_total = round(item['unit_price'] * item['quantity'], 2)
            product    = conn.execute(
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
                order_id, item['part_number'], item['product_type'],
                category, item['quantity'], item['unit_price'], line_total
            ))

        conn.commit()
        conn.close()

        print(f"💾 Order {order_number} saved (awaiting PayFast payment)")

        payfast_data = build_payfast_form_data(
            order_number   = order_number,
            total_amount   = total,
            customer_name  = data['customer_name'].strip(),
            customer_email = data['customer_email'].strip(),
            base_url       = BASE_URL
        )

        session.pop('cart', None)
        print(f"✅ Order {order_number} ready — sending customer to PayFast")

        return jsonify({
            'message'      : 'Order created! Redirecting to PayFast...',
            'order_number' : order_number,
            'payfast_url'  : payfast_data['payfast_url'],
            'form_data'    : payfast_data['form_data']
        }), 201

    except Exception as e:
        conn.close()
        print(f"❌ Order creation failed: {e}")
        return jsonify({'error': f'Order could not be created: {str(e)}'}), 500


@app.route('/api/orders', methods=['GET'])
def get_all_orders():
    """GET /api/orders — Returns all orders. For admin use."""
    conn   = get_db_connection()
    orders = conn.execute('SELECT * FROM orders ORDER BY created_at DESC').fetchall()
    conn.close()
    return jsonify([dict(row) for row in orders]), 200


@app.route('/api/orders/<order_number>', methods=['GET'])
def get_order(order_number):
    """GET /api/orders/EBC-20260419-0001 — Returns one order with items."""
    conn  = get_db_connection()
    order = conn.execute(
        'SELECT * FROM orders WHERE order_number = ?', (order_number,)
    ).fetchone()
    if order is None:
        conn.close()
        return jsonify({'error': 'Order not found'}), 404
    items           = conn.execute(
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
    conn = get_db_connection()
    rows = conn.execute(
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
        products = conn.execute('SELECT * FROM products ORDER BY part_number').fetchall()
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
           FROM vehicle_fitment vf JOIN vehicles v ON vf.vehicle_id = v.id
           WHERE vf.part_number = ? ORDER BY v.make, v.model, v.year''',
        (part_number,)
    ).fetchall()
    conn.close()
    result         = dict(product)
    result['fits'] = [dict(row) for row in fitments]
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

    sandbox = os.environ.get('PAYFAST_SANDBOX', 'true').lower() == 'true'
    mode    = "SANDBOX (Test) 🧪" if sandbox else "LIVE 🔴 — REAL MONEY!"
    print(f"💳 PayFast : {mode}")
    print(f"🌐 Base URL: {BASE_URL}")
    print(f"🚀 Starting {STORE_NAME} server...")
    print("🌐 Store   : http://localhost:5000")
    print("🛒 Cart    : http://localhost:5000/cart")
    print("🔔 ITN     : http://localhost:5000/payfast/notify")
    print("⛔ Stop    : CTRL + C\n")

    app.run(debug=True, port=5000)