import json
import os
import shutil
import sys
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db  # noqa: E402
from model import MapError, MappedRun, Row, Scope  # noqa: E402

TEST_URL = os.environ.get("TEST_DATABASE_URL", "postgresql://localhost:5432/market_radar_test")

DEFAULT_COLUMNS = {"products": {"retailer": "shop"}, "reviews": {"product_key": "p"}, "ads": {"channel": "google"}}


def ts(run_id: str) -> datetime:
    return datetime.strptime(run_id, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)


def rec(key, kind="product", table="products", scope="all", **raw) -> dict:
    return {"key": key, "kind": kind, "url": "https://example.test/" + key,
            "fetched_at": "2026-11-10T00:00:00Z", "raw": {"table": table, "scope": scope, **raw}}


def _map_run(run, records) -> MappedRun:
    rows, not_fetched = [], 0
    for r in records:
        raw = r["raw"]
        if raw.get("state") == "not_fetched":
            not_fetched += 1
            continue
        if raw.get("bad"):
            raise MapError(r["key"])
        table = raw["table"]
        rows.append(Row(table=table, kind=r["kind"], key=r["key"], scope=raw["scope"], url=r.get("url"),
                        fetched_at=r["fetched_at"], raw=raw,
                        columns=raw.get("columns", DEFAULT_COLUMNS.get(table, {}))))
    extra = run.get("extra") or {}
    if "scopes" in extra:
        scopes = [Scope(*s) for s in extra["scopes"]]
    else:
        scopes = [Scope("all", run["status"], run["reason"])]
    return MappedRun(rows=rows, scopes=scopes, not_fetched=not_fetched)


FAKE = SimpleNamespace(
    SOURCE="fake",
    ENDING={("products", "product"): "absent", ("reviews", "review"): "never", ("ads", "ad"): "source_date"},
    map_run=_map_run,
)


class DbTestCase(unittest.TestCase):
    def setUp(self):
        self.schema = "t_" + uuid.uuid4().hex[:8]
        try:
            with psycopg.connect(TEST_URL, autocommit=True) as admin:
                admin.execute(f"CREATE SCHEMA {self.schema}")
        except psycopg.OperationalError:
            self.fail(f"Postgres not reachable at {TEST_URL}")
        sep = "&" if "?" in TEST_URL else "?"
        self.url = f"{TEST_URL}{sep}options=-csearch_path%3D{self.schema}"
        self.conn = db.connect(self.url)
        db.ensure_schema(self.conn)
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        self.conn.close()
        with psycopg.connect(TEST_URL, autocommit=True) as admin:
            admin.execute(f"DROP SCHEMA {self.schema} CASCADE")
        shutil.rmtree(self.dir, ignore_errors=True)

    def write_run(self, source, brand, run_id, status="ok", records=(), reason="", extra=None) -> Path:
        folder = self.dir / source / "raw" / brand
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{run_id}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
        started = ts(run_id).isoformat().replace("+00:00", "Z")
        run = {"source": source, "brand": brand, "run_id": run_id, "started_at": started,
               "finished_at": started, "status": status, "reason": reason, "records": len(records),
               "expected_total": None, "requests": 0, "cost_usd": 0, "extra": extra or {}}
        path = folder / f"{run_id}.run.json"
        path.write_text(json.dumps(run))
        return path

    def _query(self, sql, params=()):
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def columns(self, table):
        rows = self._query("SELECT column_name FROM information_schema.columns "
                           "WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position",
                           (self.schema, table))
        return [r["column_name"] for r in rows]

    def primary_key(self, table):
        rows = self._query(
            "SELECT k.column_name FROM information_schema.table_constraints c "
            "JOIN information_schema.key_column_usage k USING (constraint_schema, constraint_name, table_name) "
            "WHERE c.constraint_type = 'PRIMARY KEY' AND c.table_schema = %s AND c.table_name = %s "
            "ORDER BY k.ordinal_position", (self.schema, table))
        return [r["column_name"] for r in rows]

    def table(self, name):
        order = ", ".join(self.primary_key(name))
        return self._query(f"SELECT * FROM {name} ORDER BY {order}")
