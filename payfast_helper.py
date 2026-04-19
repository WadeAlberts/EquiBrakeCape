# =============================================================================
# payfast_helper.py
# =============================================================================
# Handles all PayFast communication:
#   1. Building the outgoing payment form data + signature
#   2. Verifying the incoming ITN signature (FIXED in Phase 5)
#
# THE SIGNATURE FIX EXPLAINED (simply):
#
# BEFORE (broken):
#   PayFast sends ITN → Flask URL-decodes the values → we re-encode with quote_plus
#   PayFast's encoding != our re-encoding → signatures don't match ❌
#
# AFTER (fixed):
#   PayFast sends ITN → we take the RAW body exactly as PayFast sent it
#   We strip the signature field and hash the rest (same as what PayFast hashed)
#   Same input → same MD5 → signatures match ✅
# =============================================================================

import hashlib          # For creating the MD5 fingerprint
import urllib.parse     # For URL-encoding values
import os               # For reading .env variables


def get_payfast_url():
    """
    Returns the correct PayFast URL based on PAYFAST_SANDBOX in .env
    true  = sandbox.payfast.co.za (test, no real money)
    false = www.payfast.co.za     (live, real money — Phase 6 only)
    """
    sandbox = os.environ.get('PAYFAST_SANDBOX', 'true').lower() == 'true'
    if sandbox:
        return 'https://sandbox.payfast.co.za/eng/process'
    else:
        return 'https://www.payfast.co.za/eng/process'


def generate_signature(data, passphrase=None):
    """
    Creates the PayFast security signature for the OUTGOING payment form.

    This is used when we build the form to send the customer to PayFast.
    PayFast verifies this signature to confirm the form came from us.

    Rules:
      - Fields must be in the exact order they were added (no sorting)
      - Each value is URL-encoded with quote_plus (spaces → +)
      - Passphrase is appended at the end
      - MD5 hash of the whole string = the signature

    Parameters:
        data       - ordered dict of form fields
        passphrase - your PayFast passphrase from .env

    Returns:
        32-character MD5 hash string e.g. "a3f5c1d8e9b2..."
    """
    payload_parts = []

    for key, value in data.items():
        # Skip the signature field itself (we're generating it)
        if key == 'signature':
            continue
        # Skip completely empty values
        if str(value).strip() == '':
            continue
        # URL-encode the value (spaces → +, @ → %40, etc.)
        encoded_value = urllib.parse.quote_plus(str(value))
        payload_parts.append(f"{key}={encoded_value}")

    payload = '&'.join(payload_parts)

    # Append the passphrase at the end
    if passphrase and str(passphrase).strip():
        encoded_passphrase = urllib.parse.quote_plus(passphrase.strip())
        payload += f"&passphrase={encoded_passphrase}"

    signature = hashlib.md5(payload.encode('utf-8')).hexdigest()

    print(f"🔏 Outgoing signature input  : {payload}")
    print(f"🔏 Outgoing signature output : {signature}")

    return signature


def build_payfast_form_data(order_number, total_amount, customer_name, customer_email, base_url):
    """
    Builds the complete set of form fields to send the customer to PayFast.

    The field ORDER matters for the signature — PayFast expects them in
    this specific order: merchant → URLs → customer → payment details.

    Parameters:
        order_number   - e.g. "EBC-20260419-0001"
        total_amount   - e.g. 1250.00 (Rands, NOT cents)
        customer_name  - e.g. "John Smith"
        customer_email - e.g. "john@example.com"
        base_url       - e.g. "https://abc123.ngrok-free.app"

    Returns:
        {
            'form_data'   : { all fields including the signature },
            'payfast_url' : 'https://sandbox.payfast.co.za/eng/process'
        }
    """
    merchant_id  = os.environ.get('PAYFAST_MERCHANT_ID', '10000100')
    merchant_key = os.environ.get('PAYFAST_MERCHANT_KEY', '46f0cd694581a')
    passphrase   = os.environ.get('PAYFAST_PASSPHRASE',  'jt7NOE43FZPn')

    base_url = base_url.rstrip('/')

    # Split full name into first and last (PayFast needs them separate)
    name_parts = customer_name.strip().split(' ', 1)
    name_first = name_parts[0]
    name_last  = name_parts[1] if len(name_parts) > 1 else '-'

    # Build the form data in the EXACT ORDER PayFast expects
    data = {}
    data['merchant_id']   = merchant_id
    data['merchant_key']  = merchant_key
    data['return_url']    = f"{base_url}/order/confirmation/{order_number}"
    data['cancel_url']    = f"{base_url}/payment/cancelled/{order_number}"
    data['notify_url']    = f"{base_url}/payfast/notify"
    data['name_first']    = name_first
    data['name_last']     = name_last
    data['email_address'] = customer_email
    data['m_payment_id']  = order_number
    data['amount']        = f"{total_amount:.2f}"   # e.g. "1250.00"
    data['item_name']     = f"EBC Brake Parts - {order_number}"

    # Generate the signature LAST — it fingerprints all fields above
    data['signature'] = generate_signature(data, passphrase)

    print(f"📋 PayFast form built for {order_number} — R{total_amount:.2f}")
    print(f"🌐 PayFast URL: {get_payfast_url()}")

    return {
        'form_data'   : data,
        'payfast_url' : get_payfast_url()
    }


def verify_itn_signature(raw_post_body, received_signature, passphrase=None):
    """
    Verifies the ITN (Instant Transaction Notification) signature from PayFast.

    WHY WE USE THE RAW BODY:
    ========================
    When PayFast sends the ITN, they compute the signature from the raw
    URL-encoded POST values. If we URL-decode those values (what Flask does
    automatically) and then re-encode them, tiny encoding differences can
    produce a different MD5 fingerprint.

    The safest approach: take the raw POST body exactly as PayFast sent it,
    strip out the signature field, append the passphrase, and hash it.
    This guarantees we're hashing the exact same string PayFast hashed.

    Example raw body PayFast sends:
      m_payment_id=EBC-20260419-0001&pf_payment_id=3112001&...&signature=abc123

    We strip the signature field:
      m_payment_id=EBC-20260419-0001&pf_payment_id=3112001&...

    Append the passphrase:
      m_payment_id=EBC-20260419-0001&...&passphrase=jt7NOE43FZPn

    MD5 of that = should match what PayFast computed ✅

    Parameters:
        raw_post_body       - the raw string body of the POST request
        received_signature  - the signature PayFast included in their POST
        passphrase          - your PayFast passphrase from .env

    Returns:
        True if signatures match (notification is genuine)
        False if they don't match (do not process this notification!)
    """
    # -------------------------------------------------------------------------
    # Split the raw body into individual key=value pairs.
    # Keep each pair EXACTLY as-is — no decoding, no re-encoding.
    # Filter out the signature= pair since we're recalculating it.
    # -------------------------------------------------------------------------
    parts = []
    for pair in raw_post_body.split('&'):
        if '=' not in pair:
            continue
        key = pair.split('=', 1)[0]    # Get just the key name
        if key != 'signature':         # Skip the signature field
            parts.append(pair)         # Keep the raw key=value exactly

    # Rejoin all other fields
    payload = '&'.join(parts)

    # -------------------------------------------------------------------------
    # Append the passphrase at the end.
    # This IS URL-encoded because that's what PayFast does on their side.
    # -------------------------------------------------------------------------
    if passphrase and str(passphrase).strip():
        encoded_passphrase = urllib.parse.quote_plus(passphrase.strip())
        payload += f"&passphrase={encoded_passphrase}"

    # Compute the MD5 fingerprint
    computed_signature = hashlib.md5(payload.encode('utf-8')).hexdigest()

    is_valid = (computed_signature == received_signature)

    if is_valid:
        print(f"✅ PayFast ITN signature valid")
    else:
        print(f"❌ PayFast ITN signature INVALID")
        print(f"   Raw payload  : {payload}")
        print(f"   Received sig : {received_signature}")
        print(f"   Computed sig : {computed_signature}")

    return is_valid