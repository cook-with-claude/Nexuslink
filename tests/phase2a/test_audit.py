import os
from app.audit import log as audit
from app.infra import storage


def test_write_audit_inserts_row_with_timestamp(app_data_dir):
    key = os.urandom(32)
    conn = storage.connect(key)
    storage.init_schema(conn)
    audit.write_audit(conn, "nadim", audit.LOGIN_SUCCESS, {"foo": "bar"})
    conn.commit()
    row = conn.execute(
        "SELECT username, event_type, detail, ts FROM audit_log").fetchone()
    assert row["username"] == "nadim"
    assert row["event_type"] == "LOGIN_SUCCESS"
    assert "foo" in row["detail"]
    assert row["ts"]  # non-empty ISO timestamp
    conn.close()


def test_write_audit_allows_null_detail(app_data_dir):
    key = os.urandom(32)
    conn = storage.connect(key)
    storage.init_schema(conn)
    audit.write_audit(conn, "nadim", audit.LOGOUT)
    conn.commit()
    row = conn.execute("SELECT detail FROM audit_log").fetchone()
    assert row["detail"] is None
    conn.close()
