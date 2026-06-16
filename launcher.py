"""Desktop launcher for the Cairn test build.

Starts the Flask server bound to localhost on a fixed port, then opens the
default browser. This is the entry point PyInstaller bundles into the .exe.
For local testing only, not a production server.

Single instance by design: Cairn always runs at http://127.0.0.1:5000. If that
port is already taken, a Cairn server is already running, so we just open the
browser to it instead of starting a second one. (A second server on a random
port is what made an updated build look like it "did not take effect": the old
server kept serving the old pages on 5000.)
"""
import os
import socket
import sys
import threading
import webbrowser

from app import create_app


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def main():
    port = int(os.environ.get("FINANCE_PORT", "5000"))
    url = f"http://127.0.0.1:{port}/"

    if _port_in_use(port):
        print(
            "\n  Cairn is already running at " + url + "\n"
            "  Opening it in your browser.\n\n"
            "  If you just updated Cairn and still see the old version,\n"
            "  close the other Cairn window first, then start this one again.\n"
        )
        webbrowser.open(url)
        input("Press Enter to close this window...")
        return

    app = create_app()
    banner = (
        "\n  Cairn - local test server\n"
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
        input("Press Enter to close...")
        sys.exit(1)
