import urllib.request
import json
import importlib.util
import pathlib
from app import create_app

# Load root main.py explicitly to avoid picking up phase1_cdr/main.py when
# test_bridge.py has already added phase1_cdr/ to sys.path.
_ROOT = pathlib.Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("root_main", _ROOT / "main.py")
entry = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(entry)


def test_server_starts_and_health_responds(app_data_dir):
    app = create_app()
    server, thread, port = entry.start_server(app, port=0)
    try:
        entry.wait_until_ready(port, timeout=10.0)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health") as r:
            body = json.loads(r.read())
        assert body["data"]["status"] == "ok"
        assert port != 0
    finally:
        server.shutdown()
        thread.join(timeout=5)
