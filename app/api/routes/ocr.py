"""사진 → 소비기한 후보. 로그인한 사용자만 쓸 수 있게 백엔드가 OCR 서버로 전달한다.

결과는 후보일 뿐이다. 앱은 사용자가 확인한 뒤에만 expiry_source=OCR 로 저장한다.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.models import User

router = APIRouter(prefix="/ocr", tags=["ocr"])

MAX_BYTES = 8 * 1024 * 1024
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/heic", "image/heif", "image/webp"}


@router.post("/expiry")
async def read_expiry(
    image: UploadFile = File(...),
    _: User = Depends(get_current_user),
) -> dict:
    if image.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="사진 파일만 올릴 수 있어요.")
    data = await image.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="사진이 너무 커요 (최대 8MB).")

    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=settings.ocr_timeout_seconds) as client:
            response = await client.post(
                f"{settings.ocr_service_url}/expiry",
                files={"image": (image.filename or "photo.jpg", data, image.content_type)},
            )
    except httpx.HTTPError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="사진 읽기 서버에 연결할 수 없어요. 날짜를 직접 입력해 주세요.",
        ) from None
    if response.status_code != 200:
        detail = response.json().get("detail", "사진을 읽지 못했어요.") if response.content else "사진을 읽지 못했어요."
        raise HTTPException(status_code=response.status_code, detail=detail)
    return response.json()
