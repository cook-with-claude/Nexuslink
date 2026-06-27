"""Desktop entry point: Flask on an ephemeral localhost port + a PyWebView window.

Flask runs on a daemon thread; the PyWebView window is the main thread. Closing
the window returns from webview.start(), after which the server is shut down.
"""

from __future__ import annotations

import threading
import time
import urllib.request

from werkzeug.serving import make_server

from app import create_app


def start_server(app, host: str = "127.0.0.1", port: int = 0):
    server = make_server(host, port, app, threaded=True)
    actual_port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, actual_port


def wait_until_ready(port: int, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/api/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url) as r:
                if r.status == 200:
                    return
        except Exception:
            pass
        # Back off on every non-success path (including a non-200 response),
        # so a server that is up but not yet returning 200 can't hot-loop the CPU.
        time.sleep(0.05)
    raise RuntimeError("server did not become ready in time")


def main() -> None:  # pragma: no cover - requires a display
    import webview

    app = create_app()
    server, thread, port = start_server(app, port=0)
    wait_until_ready(port)
    try:
        webview.create_window("La Passion — CDR", f"http://127.0.0.1:{port}/api/health")
        webview.start()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()  # release the listening socket FD (shutdown alone doesn't)


if __name__ == "__main__":  # pragma: no cover
    main()
