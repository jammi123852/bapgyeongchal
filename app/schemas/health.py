"""health 응답 스키마.

DB 버전/호스트/스키마 등 내부 정보를 노출하지 않는다.
"""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"]


class DatabaseHealthResponse(BaseModel):
    status: Literal["ok", "error"]
    database: Literal["ok", "error"]
