"""기기별 자동 계정 (로그인 화면 제거, migration 0005).

확인 항목: 같은 키 → 같은 계정 / 다른 키 → 다른 계정(데이터 분리) / 키 형식 검증 /
DB 에 키 원문이 아니라 sha256 만 저장 / 이메일·기기키 둘 다 없는 계정은 CHECK 로 거부.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime
from collections.abc import Generator

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app
from app.models import User


@pytest.fixture
def client(db: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def new_key() -> str:
    return secrets.token_urlsafe(32)


def device_token(client: TestClient, key: str) -> str:
    response = client.post("/auth/device", json={"device_key": key})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def me(client: TestClient, token: str) -> dict:
    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    return response.json()


def test_same_key_returns_same_account(client: TestClient) -> None:
    key = new_key()
    first = me(client, device_token(client, key))
    second = me(client, device_token(client, key))
    assert first["id"] == second["id"]
    assert first["email"] is None


def test_different_keys_have_separate_inventory(client: TestClient) -> None:
    token_a = device_token(client, new_key())
    token_b = device_token(client, new_key())
    created = client.post(
        "/inventory", json={"custom_name": "우유"}, headers={"Authorization": f"Bearer {token_a}"}
    )
    assert created.status_code == 201, created.text
    item_id = created.json()["id"]

    listed_b = client.get("/inventory", headers={"Authorization": f"Bearer {token_b}"})
    assert listed_b.status_code == 200
    assert all(item["id"] != item_id for item in listed_b.json())
    other = client.get(f"/inventory/{item_id}", headers={"Authorization": f"Bearer {token_b}"})
    assert other.status_code == 404


def test_only_hash_is_stored(client: TestClient, db: Session) -> None:
    key = new_key()
    user_id = me(client, device_token(client, key))["id"]
    stored = db.scalar(sa.select(User.device_key_hash).where(User.id == user_id))
    assert stored == hashlib.sha256(key.encode("ascii")).hexdigest()
    assert stored != key


@pytest.mark.parametrize("bad", ["short", "a" * 129, "한글키" * 20, "a b" * 20, "a/b+c=" * 10])
def test_bad_key_rejected(client: TestClient, bad: str) -> None:
    response = client.post("/auth/device", json={"device_key": bad})
    assert response.status_code == 422


def test_deleted_device_account_rejected(client: TestClient, db: Session) -> None:
    key = new_key()
    user_id = me(client, device_token(client, key))["id"]
    user = db.get(User, user_id)
    user.deleted_at = datetime.now(UTC)
    db.flush()
    response = client.post("/auth/device", json={"device_key": key})
    assert response.status_code == 403


def test_account_without_identity_violates_check(db: Session) -> None:
    db.add(User())
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
