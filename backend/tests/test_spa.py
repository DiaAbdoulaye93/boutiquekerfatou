"""The built Angular app is served by FastAPI, with index.html as client-side fallback."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.config import get_settings
from app.main import create_app
from tests.fakes import factory


@pytest.fixture
def client(
    shop_db: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    monkeypatch.setattr(get_settings(), "slide_dates_on_startup", False)
    monkeypatch.setattr(get_settings(), "app_password", None)
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<app-root></app-root>", encoding="utf-8")
    (static / "chunk-ABC.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("nope", encoding="utf-8")
    with TestClient(create_app(shop_db, factory([]), static_dir=static)) as client:
        yield client


def test_serves_files_with_cache_headers(client: TestClient) -> None:
    asset = client.get("/chunk-ABC.js")
    assert asset.status_code == 200 and "immutable" in asset.headers["cache-control"]
    index = client.get("/")
    assert "<app-root>" in index.text and index.headers["cache-control"] == "no-cache"


def test_client_routes_fall_back_to_index(client: TestClient) -> None:
    assert "<app-root>" in client.get("/une/page").text


def test_api_paths_are_not_shadowed(client: TestClient) -> None:
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/api/shop").status_code == 200
    assert client.get("/api/unknown").status_code == 404


def test_no_path_traversal(client: TestClient) -> None:
    assert "nope" not in client.get("/../secret.txt").text
    assert "nope" not in client.get("/%2e%2e/secret.txt").text
