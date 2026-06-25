import urllib.request
import json
import main as entry
from app import create_app


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
