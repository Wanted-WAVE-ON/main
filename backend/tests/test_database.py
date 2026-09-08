import pytest
from sqlalchemy.exc import IntegrityError

from silent_orchestra.database import build_engine, init_db


def test_sqlite_guards_upgrade_legacy_tables_without_rebuilding_them():
    engine = build_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE contexts (id TEXT PRIMARY KEY, user_id TEXT, activity TEXT)"
        )
        connection.exec_driver_sql(
            """CREATE TABLE gesture_patterns (
                   id TEXT PRIMARY KEY, user_id TEXT, gesture_key TEXT,
                   context_scope TEXT, status TEXT
               )"""
        )
        connection.exec_driver_sql(
            """CREATE TABLE feedback (
                   id TEXT PRIMARY KEY, gesture_pattern_id TEXT,
                   execution_id TEXT, created_at TEXT
               )"""
        )
    init_db(engine)

    with engine.begin() as connection:
        with pytest.raises(IntegrityError):
            connection.exec_driver_sql(
                "INSERT INTO contexts (id, activity) VALUES ('ctx', 'browser')"
            )
        with pytest.raises(IntegrityError):
            connection.exec_driver_sql(
                "INSERT INTO gesture_patterns (id, context_scope) VALUES ('pat', 'other')"
            )
        connection.exec_driver_sql(
            "INSERT INTO feedback (id, execution_id) VALUES ('fb-1', 'execution')"
        )
        with pytest.raises(IntegrityError):
            connection.exec_driver_sql(
                "INSERT INTO feedback (id, execution_id) VALUES ('fb-2', 'execution')"
            )

    engine.dispose()
