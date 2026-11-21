import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sqlite_tools import snapshot_database, validate_database


class StandbySQLiteToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.database = self.root / "class-merit.sqlite3"
        with sqlite3.connect(self.database) as connection:
            for table in ("users", "scores", "evaluations", "login_throttle", "audit_logs"):
                connection.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, value TEXT)")
            connection.execute("INSERT INTO users(value) VALUES ('test-user')")

    def tearDown(self):
        self.temp.cleanup()

    def test_validate_accepts_complete_database(self):
        validate_database(self.database)

    def test_snapshot_preserves_data_and_is_valid(self):
        snapshot = self.root / "snapshot.sqlite3"
        snapshot_database(self.database, snapshot)
        validate_database(snapshot)
        with sqlite3.connect(snapshot) as connection:
            value = connection.execute("SELECT value FROM users").fetchone()[0]
        self.assertEqual(value, "test-user")

    def test_validate_rejects_incomplete_database(self):
        incomplete = self.root / "incomplete.sqlite3"
        with sqlite3.connect(incomplete) as connection:
            connection.execute("CREATE TABLE users (id INTEGER)")
        with self.assertRaises(RuntimeError):
            validate_database(incomplete)


if __name__ == "__main__":
    unittest.main()
