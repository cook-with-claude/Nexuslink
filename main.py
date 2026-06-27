"""Desktop entry point: Flask on an ephemeral localhost port + a PyWebView window.

Flask runs on a daemon thread; the PyWebView window is the main thread. Closing
the window returns from webview.start(), after which the server is shut down.

Phase 2B summary (the desktop UI layer; backend Phase 2A is byte-untouched):
  WHAT WAS BUILT — a vanilla no-build SPA (hand-written HTML/CSS/JS, hash router)
  served same-origin by Flask via the new `app/ui.py` blueprint, registered HERE
  after create_app() so app/__init__.py and every Phase 2A module stay frozen.
  Screens: login/first-run, dashboard, datasets, import, targets (per dataset),
  results, change-password. Aesthetic: dark data-terminal, monospace for all data,
  4-state confidence pill, gate trace rendered as labeled rows (never raw JSON).

  API MISMATCHES handled (each also tagged `API-MISMATCH:` in the JS):
    #1  no HTML served by Phase 2A  -> new ui_bp serves index.html + assets at /.
    #2  no stats endpoint           -> dashboard derives from datasets+targets.
    #3  /api/targets is global      -> filtered by dataset_id client-side.
    #4  add-target phone must exist  -> picker from /datasets/<id>/phone-numbers;
                                        dataset_id sent as a number.
    #5  confidence has 4 states     -> "Insufficient data" gets its own pill.
    #6  analyze omits dataset name  -> joined client-side via /targets+/datasets.
    #7  401 is overloaded           -> redirect to login EXCEPT on login &
                                        change-password, where 401 shows inline.
    #8  freq_contacts + areas_conf  -> both rendered (contacts table + area pill).
    #9  near_tie / alternatives     -> surfaced as a tag + list (display only).
    #10 logout unused in brief      -> logout control in the top nav.
    #11 content-type guard (415)    -> JSON calls set the header; import uses
                                        FormData and lets the browser set it.
    #12 bcrypt 72-byte limit (400)  -> surfaced inline on setup/change-password.

  DEVIATIONS: none from the agreed plan.
  FOLLOW-UPS (out of scope, flagged): re-analysis history/trend, cross-dataset
  target search, CSV/PDF export, multi-account, light theme.
"""

from __future__ import annotations

import threading
import time
import urllib.request

from werkzeug.serving import make_server

from app import create_app
from app.ui import bp as ui_bp


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
    app.register_blueprint(ui_bp)  # additive UI layer; Phase 2A factory untouched
    server, thread, port = start_server(app, port=0)
    wait_until_ready(port)
    try:
        webview.create_window("La Passion — CDR Analysis", f"http://127.0.0.1:{port}/")
        webview.start()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()  # release the listening socket FD (shutdown alone doesn't)


if __name__ == "__main__":  # pragma: no cover
    main()
