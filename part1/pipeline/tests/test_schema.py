import unittest

import support
import db
import model

TABLES = ("ads", "products", "reviews", "search_rankings", "search_interest", "posts", "runs", "run_scopes", "changes", "ad_angles")


class SchemaTest(support.DbTestCase):
    def test_tables_and_columns(self):
        for table, own in model.TABLE_COLUMNS.items():
            self.assertEqual(self.columns(table), list(model.COMMON_COLUMNS + own))
        self.assertEqual(self.columns("runs"), ["source", "brand", "run_id", "started_at", "finished_at",
            "status", "reason", "records", "expected_total", "requests", "cost_usd", "extra", "result", "loaded_at"])
        self.assertEqual(self.columns("run_scopes"), ["source", "brand", "run_id", "scope", "status", "reason"])

    def test_primary_keys(self):
        self.assertEqual(self.primary_key("products"), ["source", "brand", "kind", "key"])
        self.assertEqual(self.primary_key("runs"), ["source", "brand", "run_id"])
        self.assertEqual(self.primary_key("run_scopes"), ["source", "brand", "run_id", "scope"])

    def test_ensure_schema_twice(self):
        db.ensure_schema(self.conn)   # the second time; setUp ran the first
        found = [r["table_name"] for r in self._query(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = %s AND table_type = 'BASE TABLE'", (self.schema,))]
        self.assertEqual(sorted(found), sorted(TABLES))


if __name__ == "__main__":
    unittest.main()
