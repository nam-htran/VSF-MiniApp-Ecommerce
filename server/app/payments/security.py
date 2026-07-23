"""The IPN signature.

The payment gateway signs each notification with an HMAC over the fields
that matter — order, amount, status — using a secret both sides share.
The receiver recomputes it and compares in constant time, so a forged or
altered notification is rejected before it can mark anything paid.
"""

import hashlib
import hmac


def compute_hash(secret: str, order_id: str, amount: int, status: str) -> str:
    message = f"{order_id}|{amount}|{status}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify_hash(
    secret: str, order_id: str, amount: int, status: str, provided: str
) -> bool:
    expected = compute_hash(secret, order_id, amount, status)
    return hmac.compare_digest(expected, provided or "")
