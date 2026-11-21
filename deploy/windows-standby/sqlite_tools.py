"""Validate and snapshot Class Merit Hub SQLite databases for standby recovery."""
from __future__ import annotations
import argparse
import sqlite3
import sys
from pathlib import Path

REQUIRED_TABLES = {"users", "scores", "evaluations", "login_throttle", "audit_logs"}

def connect_database(path: Path) -> sqlite3.Connection:
    if not path.is_file() or path.stat().st_size == 0:
        raise FileNotFoundError(f"Database does not exist or is empty: {path}")
    return sqlite3.connect(str(path), timeout=60)

def validate_database(path: Path) -> None:
    connection = connect_database(path)
    try:
        result = connection.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise RuntimeError(f"SQLite integrity_check failed: {result!r}")
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        missing = sorted(REQUIRED_TABLES - tables)
        if missing:
            raise RuntimeError("Missing required Class Merit Hub tables: " + ", ".join(missing))
    finally:
        connection.close()

def snapshot_database(source_path: Path, destination_path: Path) -> None:
    """Create a consistent SQLite snapshot, including committed WAL contents."""
    if source_path.resolve() == destination_path.resolve():
        raise ValueError("Source and snapshot paths must be different.")
    source = connect_database(source_path)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    if destination_path.exists():
        destination_path.unlink()
    destination = sqlite3.connect(str(destination_path), timeout=60)
    try:
        source.backup(destination, pages=256, sleep=0.05)
        result = destination.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise RuntimeError(f"Snapshot integrity_check failed: {result!r}")
    except Exception:
        destination.close()
        destination_path.unlink(missing_ok=True)
        raise
    finally:
        try:
            destination.close()
        except Exception:
            pass
        source.close()
    validate_database(destination_path)

def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("database", type=Path)
    snapshot_parser = subparsers.add_parser("snapshot")
    snapshot_parser.add_argument("source", type=Path)
    snapshot_parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    if args.command == "validate":
        validate_database(args.database)
        print("SQLite integrity and Class Merit Hub schema checks passed.")
    else:
        snapshot_database(args.source, args.destination)
        print(f"Consistent SQLite snapshot created: {args.destination}")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
