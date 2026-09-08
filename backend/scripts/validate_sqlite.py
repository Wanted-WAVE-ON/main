#!/usr/bin/env python3
"""Execute and validate SQLite schema, seed, queries, and smoke tests."""

import argparse
import json
import sqlite3
import sys
from collections.abc import Iterator
from pathlib import Path


def iter_statements(sql_text: str) -> Iterator[str]:
    """Split SQL using sqlite3.complete_statement while preserving SQL syntax."""
    buffer: list[str] = []
    for line in sql_text.splitlines(keepends=True):
        buffer.append(line)
        candidate = "".join(buffer).strip()
        if candidate and sqlite3.complete_statement(candidate):
            yield candidate
            buffer.clear()
    remainder = "".join(buffer).strip()
    if remainder:
        # SQLite accepts a final statement without a semicolon.
        yield remainder


def preview(sql: str, limit: int = 180) -> str:
    single_line = " ".join(sql.split())
    return single_line if len(single_line) <= limit else single_line[: limit - 3] + "..."


def check_test_assertion(statement: str, columns: list[str], rows: list) -> tuple[bool, str | None]:
    """Apply optional semantic assertions for statements in tests.sql.

    Supported conventions:
    - PRAGMA foreign_key_check must return zero rows.
    - A SELECT whose first column is named ok/pass/passed or assert_* must
      return exactly one row with a truthy first value.
    Other statements are treated as execution-only smoke tests.
    """
    if " ".join(statement.strip().lower().split()).startswith("pragma foreign_key_check"):
        if rows:
            return False, "PRAGMA foreign_key_check returned violations"
        return True, "foreign_key_check returned no violations"

    first_column = columns[0].strip().lower() if columns else ""
    if not (first_column in {"ok", "pass", "passed"} or first_column.startswith("assert_")):
        return True, None
    if len(rows) != 1:
        return False, "Assertion query must return exactly one row"
    if not bool(rows[0][0]):
        return False, f"Assertion column '{columns[0]}' evaluated to a false value"
    return True, f"Assertion column '{columns[0]}' evaluated to true"


def execute_file(conn: sqlite3.Connection, path: Path, label: str) -> tuple[list[dict], str | None]:
    """Run every statement in `path`, stopping at the first failure."""
    results: list[dict] = []
    for index, statement in enumerate(iter_statements(path.read_text(encoding="utf-8")), start=1):
        result: dict = {
            "source": label,
            "index": index,
            "sql_preview": preview(statement),
            "status": "passed",
            "columns": [],
            "row_count": None,
            "rows_preview": [],
            "error": None,
            "assertion": None,
        }
        results.append(result)
        try:
            cursor = conn.execute(statement)
        except sqlite3.Error as exc:
            result.update(status="failed", error=str(exc))
            return results, result["error"]

        if cursor.description:
            result["columns"] = [column[0] for column in cursor.description]
            result["rows_preview"] = [list(row) for row in cursor.fetchmany(5)]
            result["row_count"] = len(result["rows_preview"])
        else:
            result["row_count"] = cursor.rowcount

        if label == "tests":
            passed, result["assertion"] = check_test_assertion(
                statement, result["columns"], result["rows_preview"]
            )
            if not passed:
                result.update(status="failed", error=result["assertion"])
                return results, result["error"]
    return results, None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--seed", type=Path)
    parser.add_argument("--queries", type=Path)
    parser.add_argument("--tests", type=Path)
    parser.add_argument("--database", type=Path, help="Optional SQLite DB path; defaults to memory")
    parser.add_argument("--report", type=Path, default=Path("validation-report.json"))
    args = parser.parse_args()

    database = str(args.database) if args.database else ":memory:"
    args.report.parent.mkdir(parents=True, exist_ok=True)
    all_results: list[dict] = []
    failure: str | None = None

    try:
        with sqlite3.connect(database) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("BEGIN")
            for path, label in (
                (args.schema, "schema"),
                (args.seed, "seed"),
                (args.queries, "queries"),
                (args.tests, "tests"),
            ):
                if path is None:
                    continue
                results, error = execute_file(conn, path, label)
                all_results.extend(results)
                if error:
                    failure = f"{label}: {error}"
                    break
            conn.rollback()
    except (OSError, sqlite3.Error) as exc:
        failure = str(exc)

    report = {
        "database": database,
        "status": "failed" if failure else "passed",
        "foreign_keys": True,
        "transaction_rolled_back": True,
        "statement_count": len(all_results),
        "failure": failure,
        "test_conventions": {
            "foreign_key_check": "must return zero rows",
            "assertion_columns": "ok/pass/passed/assert_* must return one truthy value",
        },
        "results": all_results,
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"SQLite validation: {report['status']}")
    print(f"Statements executed: {len(all_results)}")
    print(f"Report: {args.report.resolve()}")
    if failure:
        print(f"Failure: {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
