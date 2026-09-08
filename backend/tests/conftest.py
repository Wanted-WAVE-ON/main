import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from silent_orchestra.database import Base, build_engine, get_db  # noqa: E402
from silent_orchestra.main import app  # noqa: E402


@pytest.fixture()
def db_engine():
    engine = build_engine("sqlite://")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def testing_session(db_engine):
    return sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def db_session(testing_session):
    with testing_session() as db:
        yield db


@pytest.fixture()
def client(testing_session):
    def override_get_db():
        with testing_session() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        # The lifespan seeds the real database, not this per-test one.
        assert test_client.post("/api/v1/demo/bootstrap").status_code == 200
        yield test_client
    app.dependency_overrides.clear()
