"""Helpers for human-readable HTTP status code labels."""
from http import HTTPStatus


def http_status_label(code):
    """Return a compact label such as '404 – Not Found · Client Error'."""
    if code in (None, "", "—", "N/A"):
        return "—"
    try:
        numeric_code = int(code)
    except (TypeError, ValueError):
        return str(code)

    try:
        phrase = HTTPStatus(numeric_code).phrase
    except ValueError:
        phrase = "Unknown Status"

    if 100 <= numeric_code <= 199:
        category = "Informational"
    elif 200 <= numeric_code <= 299:
        category = "Success"
    elif 300 <= numeric_code <= 399:
        category = "Redirection"
    elif 400 <= numeric_code <= 499:
        category = "Client Error"
    elif 500 <= numeric_code <= 599:
        category = "Server Error"
    else:
        category = "Unknown Category"

    return f"{numeric_code} – {phrase} · {category}"
