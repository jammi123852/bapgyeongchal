"""백엔드 /ocr/expiry 검증. 실제 OCR 서버 대신 가짜 응답(MockTransport)을 쓴다."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.routes import ocr as ocr_route
from tests.conftest import signup_headers

JPEG = b"\xff\xd8\xff\xe0fake-jpeg"
OCR_OK = {
    "best": {"date": "2026-10-05", "precision": "day", "raw": "2026.10.05", "near_keyword": True, "ambiguous": False},
    "candidates": [],
    "lines": ["2026.10.05까지"],
    "seconds": 1.2,
    "engine": "fake",
}


@pytest.fixture
def fake_ocr(monkeypatch: pytest.MonkeyPatch):
    """OCR 서버 응답을 흉내 낸다. 받은 요청을 기록한다."""
    seen: list[httpx.Request] = []
    state = {"status": 200, "body": OCR_OK, "fail": False}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if state["fail"]:
            raise httpx.ConnectError("down")
        return httpx.Response(state["status"], json=state["body"])

    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        return real_client(transport=httpx.MockTransport(handler), timeout=kwargs.get("timeout"))

    monkeypatch.setattr(ocr_route.httpx, "AsyncClient", client_factory)
    return seen, state


def upload(api: TestClient, headers: dict[str, str] | None, content_type: str = "image/jpeg", data: bytes = JPEG):
    return api.post(
        "/ocr/expiry", files={"image": ("p.jpg", data, content_type)}, headers=headers or {}
    )


def test_returns_ocr_candidates(api: TestClient, fake_ocr) -> None:
    seen, _ = fake_ocr
    response = upload(api, signup_headers(api))

    assert response.status_code == 200
    assert response.json()["best"]["date"] == "2026-10-05"
    assert len(seen) == 1 and seen[0].url.path == "/expiry"
    assert JPEG in seen[0].content


def test_requires_login(api: TestClient, fake_ocr) -> None:
    seen, _ = fake_ocr

    assert upload(api, None).status_code == 401
    assert seen == []


def test_rejects_non_images(api: TestClient, fake_ocr) -> None:
    seen, _ = fake_ocr

    assert upload(api, signup_headers(api), content_type="application/pdf").status_code == 415
    assert seen == []


def test_rejects_too_large(api: TestClient, fake_ocr) -> None:
    big = b"\xff" * (ocr_route.MAX_BYTES + 1)

    assert upload(api, signup_headers(api), data=big).status_code == 413


def test_service_down_is_503(api: TestClient, fake_ocr) -> None:
    _, state = fake_ocr
    state["fail"] = True

    response = upload(api, signup_headers(api))

    assert response.status_code == 503
    assert "직접 입력" in response.json()["detail"]


def test_service_error_is_passed_through(api: TestClient, fake_ocr) -> None:
    _, state = fake_ocr
    state.update(status=422, body={"detail": "이미지를 읽을 수 없어요."})

    response = upload(api, signup_headers(api))

    assert response.status_code == 422
    assert response.json()["detail"] == "이미지를 읽을 수 없어요."
