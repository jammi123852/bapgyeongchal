"""애플리케이션 설정.

secret 은 코드에 넣지 않는다. 모든 값은 환경변수 또는 .env 에서 읽는다.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """환경변수 기반 설정.

    DATABASE_URL 은 필수이며 기본값을 코드에 두지 않는다.
    (기본값을 두면 잘못된 DB 에 조용히 연결될 수 있다.)
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "SoloSafe"
    app_version: str = "0.1.0"

    database_url: str
    test_database_url: str | None = None

    # SQLAlchemy echo. 로컬 디버깅용이며 기본은 꺼둔다.
    sql_echo: bool = False

    # 인증 (Step 3). JWT_SECRET 은 필수이며 기본값을 두지 않는다.
    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    # 모바일 앱 v0.1 은 refresh token 없이 access token 하나로 운영한다.
    access_token_expire_minutes: int = 60 * 24 * 7

    # Eat-First 기본 알고리즘 (baseline0 | baseline1). algorithm_version 으로 행마다 기록된다.
    eat_first_algorithm: str = "baseline1"

    # 브라우저(Expo web) 개발용 허용 origin. 네이티브 앱은 CORS 와 무관하다.
    cors_origins: list[str] = ["http://localhost:8081", "http://127.0.0.1:8081"]


@lru_cache
def get_settings() -> Settings:
    """설정 싱글턴. 테스트에서 환경변수를 바꾼 경우 cache_clear() 로 초기화한다."""
    return Settings()  # type: ignore[call-arg]
