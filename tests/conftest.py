"""Shared pytest fixtures: a fresh in-memory SQLite for each test, plus a
TestClient that uses it instead of the on-disk dev DB.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app import db as db_module
from app.db import get_session
from app.main import app
from app import models  # noqa: F401  (registers models on metadata)


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


@pytest.fixture
def client(engine, monkeypatch):
    def override_get_session():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = override_get_session

    # The lifespan hook would otherwise create the on-disk DB; point its
    # engine at our in-memory one for the duration of the test.
    monkeypatch.setattr(db_module, "engine", engine)

    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
