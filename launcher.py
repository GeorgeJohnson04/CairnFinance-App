
"""Desktop launcher for the Cairn test build.

Starts the Flask server bound to localhost on a free port, then opens the
default browser. This is the entry point PyInstaller bundles into the .exe.
For local testing only — not a production server.
"""
import os
import socket
import sys
import threading
import webbrowser

from app import create_app


def _free_port(preferred: int = 5000) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]


def main():
    app = create_app()
    port = _free_port(int(os.environ.get("FINANCE_PORT", "5000")))
    url = f"http://127.0.0.1:{port}/"

    banner = (
        "\n  Cairn — local test server\n"
        f"  Open in your browser:  {url}\n"
        "  (Your data is stored in the 'Cairn-data' folder "
        "next to this app.)\n"
        "  Close this window to stop the server.\n"
    )
    print(banner)

    # open the browser shortly after the server starts
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    # threaded dev server; debug off so the bundle never exposes a debugger
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True,
            use_reloader=False)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # keep the console open so testers see the error
        print(f"\nCairn failed to start: {exc}\n")
        input("Press Enter to close…")
        sys.exit(1)
