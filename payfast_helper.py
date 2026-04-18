# =============================================================================
# payfast_helper.py
# =============================================================================
# Handles everything PayFast-related:
#   1. Building the payment form data (all the fields PayFast needs)
#   2. Generating the security signature (a fingerprint to prove it came from us)
#   3. Verifying the ITN notification (to prove it came from PayFast)
#
# HOW THE SIGNATURE WORKS (simply):
#   Imagine writing all your order fields in a specific order on a piece of paper:
#     merchant_id=10000100&merchant_key=46f0cd694581a&amount=1250.00&...
#   Then you add your secret passphrase at the end.
#   Then you run the whole string through an MD5 scrambler.
#   The result is a unique 32-character fingerprint — the signature.
#
#   PayFast does the EXACT same calculation on their side.
#   If the fingerprints match — the data is genuine and untampered.
#   If they don't match — PayFast rejects the payment (which is what was happening).
#
# ⚠️ CRITICAL RULE: The fields MUST be in the exact same order on both sides.
#    PayFast does NOT sort them. We must NOT sort them either.
#    The previous version sorted alphabetically — that broke everything.
# =============================================================================

import hashlib          # For creating the MD5 fingerprint
import urllib.parse     # For URL-encoding values
import os               # For reading .env variables


def get_payfast_url():
    """
    Returns the correct PayFast URL based on sandbox mode setting in .env
    Sandbox = test mode, no real money moves.
    """
    sandbox = os.environ.get('PAYFAST_SANDBOX', 'true').lower() == 'true'
    if sandbox:
        return 'https://sandbox.payfast.co.za/eng/process'
    else:
        return 'https://www.payfast.co.za/eng/process'


def generate_signature(data, passphrase=None):
    """
    Creates the PayFast security signature.

    IMPORTANT: Fields must stay in the exact order they were added to the
    dictionary. We iterate data.items() directly — NO sorting.

    Parameters:
        data       - ordered dictionary of form fields
        passphrase - the PayFast passphrase from your .env file

    Returns:
        A 32-character MD5 hash string e.g. "a3f5c1d8e9b2..."
    """
    payload_parts = []

    # -------------------------------------------------------------------------
    # Loop through fields IN ORDER — do NOT sort them
    # PayFast calculates the signature in the same order fields were submitted
    # Sorting would produce a different fingerprint = signature mismatch error
    # -------------------------------------------------------------------------
    for key, value in data.items():

        # Skip the signature field itself (we're generating it)
        if key == 'signature':
            continue

        # Skip completely empty values
        # Note: "0" and "0.00" are NOT empty — only truly blank strings
        if str(value).strip() == '':
            continue

        # URL-encode the value
        # This converts spaces to + and special characters to %XX
        # e.g. "John Smith" becomes "John+Smith"
        encoded_value = urllib.parse.quote_plus(str(value))
        payload_parts.append(f"{key}={encoded_value}")

    # Join all parts with & between them
    # e.g. "merchant_id=10000100&merchant_key=46f0cd694581a&amount=1250.00"
    payload = '&'.join(payload_parts)

    # Append the passphrase at the very end (if one is set)
    # The passphrase acts like a secret password that only you and PayFast know
    if passphrase and str(passphrase).strip():
        encoded_passphrase = urllib.parse.quote_plus(passphrase.strip())
        payload += f"&passphrase={encoded_passphrase}"

    # Run the whole string through MD5 to get the signature fingerprint
    signature = hashlib.md5(payload.encode('utf-8')).hexdigest()

    # Print for debugging — you can see this in your terminal when testing
    print(f"🔏 Signature input  : {payload}")
    print(f"🔏 Signature output : {signature}")

    return signature


def build_payfast_form_data(order_number, total_amount, customer_name, customer_email, base_url):
    """
    Builds the complete set of form fields that PayFast needs.

    The ORDER fields are added to this dictionary matters for the signature.
    PayFast expects merchant details first, then URLs, then customer, then payment.
    We match that exact order here.

    Parameters:
        order_number   - e.g. "EBC-20250418-0001"
        total_amount   - e.g. 1250.00 (Rands, not cents)
        customer_name  - e.g. "John Smith"
        customer_email - e.g. "john@example.com"
        base_url       - e.g. "https://abc123.ngrok-free.app"

    Returns:
        {
            'form_data'   : { all fields including signature },
            'payfast_url' : 'https://sandbox.payfast.co.za/eng/process'
        }
    """
    # Read credentials from .env file
    merchant_id  = os.environ.get('PAYFAST_MERCHANT_ID', '10000100')
    merchant_key = os.environ.get('PAYFAST_MERCHANT_KEY', '46f0cd694581a')
    passphrase   = os.environ.get('PAYFAST_PASSPHRASE',  'jt7NOE43FZPn')

    base_url = base_url.rstrip('/')

    # Split full name into first and last name
    # PayFast needs them as separate fields
    name_parts = customer_name.strip().split(' ', 1)
    name_first = name_parts[0]
    name_last  = name_parts[1] if len(name_parts) > 1 else '-'

    # -------------------------------------------------------------------------
    # Build the form data IN THIS EXACT ORDER.
    #
    # Why does order matter?
    # Python dictionaries keep their insertion order (since Python 3.7).
    # When we loop through this dict to generate the signature,
    # the fields must appear in the same order that PayFast expects.
    #
    # If you ever add new fields, add them at the END before the signature step
    # and check PayFast's documentation for where they belong.
    # -------------------------------------------------------------------------
    data = {}

    # 1. Merchant details (who we are)
    data['merchant_id']   = merchant_id
    data['merchant_key']  = merchant_key

    # 2. Redirect URLs (where to send the customer after payment)
    data['return_url']    = f"{base_url}/order/confirmation/{order_number}"
    data['cancel_url']    = f"{base_url}/payment/cancelled/{order_number}"
    data['notify_url']    = f"{base_url}/payfast/notify"

    # 3. Customer details (PayFast pre-fills their form with these)
    data['name_first']    = name_first
    data['name_last']     = name_last
    data['email_address'] = customer_email

    # 4. Order / payment details
    data['m_payment_id']  = order_number
    # Amount must be formatted as "1250.00" — exactly 2 decimal places, no currency symbol
    data['amount']        = f"{total_amount:.2f}"
    data['item_name']     = f"EBC Brake Parts - {order_number}"

    # -------------------------------------------------------------------------
    # 5. Generate the signature LAST, after all other fields are added
    #    The signature is a fingerprint of all the fields above.
    # -------------------------------------------------------------------------
    data['signature'] = generate_signature(data, passphrase)

    print(f"📋 PayFast form built for {order_number} — R{total_amount:.2f}")
    print(f"🌐 PayFast URL: {get_payfast_url()}")

    return {
        'form_data'   : data,
        'payfast_url' : get_payfast_url()
    }


def verify_itn_signature(post_data, passphrase=None):
    """
    Verifies that an ITN (Instant Transaction Notification) came from PayFast.

    When PayFast sends our server the "payment done" notification,
    they include a signature. We recalculate it ourselves using the same data.
    If our calculation matches theirs — the notification is genuine.

    Parameters:
        post_data  - the form data PayFast POSTed to /payfast/notify
        passphrase - our PayFast passphrase from .env

    Returns:
        True if valid, False if suspicious
    """
    received_signature = post_data.get('signature', '')

    # Make a copy of the data without the signature field
    # (we're about to recalculate what it should be)
    data_to_verify = {k: v for k, v in post_data.items() if k != 'signature'}

    # Recalculate the expected signature
    expected_signature = generate_signature(data_to_verify, passphrase)

    is_valid = (received_signature == expected_signature)

    if is_valid:
        print(f"✅ PayFast ITN signature is valid")
    else:
        print(f"❌ PayFast ITN signature INVALID")
        print(f"   Received : {received_signature}")
        print(f"   Expected : {expected_signature}")

    return is_valid