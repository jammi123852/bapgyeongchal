"""애플리케이션 설정.

secret 은 코드에 넣지 않는다. 모든 값은 환경변수 또는 .env 에서 읽는다.
"""

from functools import lru_cache

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


@lru_cache
def get_settings() -> Settings:
    """설정 싱글턴. 테스트에서 환경변수를 바꾼 경우 cache_clear() 로 초기화한다."""
    return Settings()  # type: ignore[call-arg]
