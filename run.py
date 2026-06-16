"""Entry point for the Cairn web app.

Usage:
    python run.py            # http://127.0.0.1:5000
    set FINANCE_PORT=8080 && python run.py
"""
import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    host = os.environ.get("FINANCE_HOST", "127.0.0.1")
    port = int(os.environ.get("FINANCE_PORT", "5000"))
    # Debug mode is opt-in only: the werkzeug debugger must never be
    # exposed on a machine holding financial data.
    debug = os.environ.get("FINANCE_DEBUG", "") == "1"
    app.run(host=host, port=port, debug=debug)
