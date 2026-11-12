"""이메일 인증 검증 (Step 3).

완료조건(docs/mvp-v0_1-freeze.md 11절 Step 3): 타 사용자 데이터 접근 차단.
재고 API 는 Step 4 에서 생기므로, 여기서는 '토큰이 정확히 한 사용자에게만 묶이는지'를 검증한다.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import jwt
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models import User

PASSWORD = "correct-horse-1"


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


def signup(client: TestClient, email: str, password: str = PASSWORD) -> str:
    response = client.post("/auth/signup", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_signup_then_me(client: TestClient) -> None:
    token = signup(client, "a@example.com")

    response = client.get("/me", headers=auth(token))

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "a@example.com"
    assert body["timezone"] == "Asia/Seoul"
    assert "password_hash" not in body


def test_password_is_stored_hashed(client: TestClient, db: Session) -> None:
    signup(client, "hash@example.com")

    stored = db.scalar(sa.select(User.password_hash).where(User.email == "hash@example.com"))

    assert stored is not None
    assert PASSWORD not in stored
    assert stored.startswith("$2")


def test_email_is_normalized_and_unique(client: TestClient) -> None:
    signup(client, "Dup@Example.com")

    response = client.post(
        "/auth/signup", json={"email": "  dup@example.COM ", "password": PASSWORD}
    )

    assert response.status_code == 409


@pytest.mark.parametrize(
    "password",
    ["short", "가" * 25],  # 8자 미만 / 72 byte 초과(한글 25자 = 75 byte)
)
def test_signup_rejects_bad_password(client: TestClient, password: str) -> None:
    response = client.post("/auth/signup", json={"email": "p@example.com", "password": password})

    assert response.status_code == 422


def test_login_success_and_failures_look_the_same(client: TestClient) -> None:
    signup(client, "login@example.com")

    ok = client.post("/auth/login", json={"email": "LOGIN@example.com", "password": PASSWORD})
    wrong_pw = client.post("/auth/login", json={"email": "login@example.com", "password": "x" * 10})
    no_user = client.post("/auth/login", json={"email": "none@example.com", "password": PASSWORD})

    assert ok.status_code == 200
    assert ok.json()["token_type"] == "bearer"
    # 가입 여부가 드러나지 않도록 두 실패는 같은 응답이어야 한다.
    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json() == no_user.json()


def test_token_is_bound_to_its_own_user(client: TestClient) -> None:
    token_a = signup(client, "owner-a@example.com")
    token_b = signup(client, "owner-b@example.com")

    me_a = client.get("/me", headers=auth(token_a)).json()
    me_b = client.get("/me", headers=auth(token_b)).json()

    assert me_a["email"] == "owner-a@example.com"
    assert me_b["email"] == "owner-b@example.com"
    assert me_a["id"] != me_b["id"]


def test_logout_invalidates_existing_token(client: TestClient) -> None:
    token = signup(client, "logout@example.com")

    assert client.post("/auth/logout", headers=auth(token)).status_code == 204
    assert client.get("/me", headers=auth(token)).status_code == 401

    # 다시 로그인하면 새 토큰은 동작한다.
    new = client.post("/auth/login", json={"email": "logout@example.com", "password": PASSWORD})
    assert client.get("/me", headers=auth(new.json()["access_token"])).status_code == 200


def test_deleted_user_cannot_use_token_or_login(client: TestClient, db: Session) -> None:
    token = signup(client, "deleted@example.com")
    user = db.scalar(sa.select(User).where(User.email == "deleted@example.com"))
    assert user is not None
    user.deleted_at = datetime.now(UTC)
    db.flush()

    assert client.get("/me", headers=auth(token)).status_code == 401
    login = client.post("/auth/login", json={"email": "deleted@example.com", "password": PASSWORD})
    assert login.status_code == 401


def test_missing_or_bad_tokens_are_rejected(client: TestClient) -> None:
    settings = get_settings()
    unknown_user_token, _ = create_access_token(uuid.uuid4(), 0)
    expired = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "ver": 0,
            "exp": datetime.now(UTC) - timedelta(minutes=1),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    forged = jwt.encode(
        {"sub": str(uuid.uuid4()), "ver": 0, "exp": datetime.now(UTC) + timedelta(hours=1)},
        "x" * 48,
        algorithm="HS256",
    )

    assert client.get("/me").status_code == 401
    for token in ["garbage", unknown_user_token, expired, forged]:
        assert client.get("/me", headers=auth(token)).status_code == 401
