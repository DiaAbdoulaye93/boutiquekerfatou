"""Shared fixtures: a PostgreSQL test database (TEST_DATABASE_URL) holding a seeded shop."""

from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine

from app import models  # noqa: F401 - registers the tables
from app.config import get_settings
from app.seed.generate import clear_database, seed_database

TODAY = date(2026, 11, 13)  # a Friday
SEED_DAYS = 60


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    engine = create_engine(get_settings().test_database_url, pool_pre_ping=True)
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def shop_db(engine: Engine) -> Engine:
    """A shop generated up to TODAY. Read-only: tests that write use `fresh_db`."""
    clear_database(engine)
    seed_database(engine, end=TODAY, days=SEED_DAYS)
    return engine


@pytest.fixture
def session(shop_db: Engine) -> Iterator[Session]:
    with Session(shop_db) as session:
        yield session


@pytest.fixture
def fresh_db(engine: Engine) -> Iterator[Engine]:
    clear_database(engine)
    yield engine
    clear_database(engine)
