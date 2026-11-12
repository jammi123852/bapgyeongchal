# SoloSafe — v0.1 (Step 1: local foundation)

1인 가구가 냉장고에 넣어둔 식품을 잊어 소비기한을 넘기고 버리는 문제를 다루는 서비스의
백엔드 기반입니다.

**현재 단계는 Step 1(로컬 개발 기반 + PostgreSQL 데이터 계층)까지입니다.**
바코드 / OCR / 레시피 / 알림 / ML / 회수제품 / 건강 기능은 **구현되어 있지 않습니다.**

설계 근거 문서:


---

## 1. 필요 환경

| 항목 | 버전 | 확인됨 |
|---|---|---|
| Python | 3.12.3 | ✅ 실행 확인 |
| Docker / Docker Compose | PostgreSQL 16 컨테이너 실행용 | ⚠ **현재 개발 환경에 미설치 — 아래 3-2 참고** |
| PostgreSQL | 16 (Docker) | ⚠ 미기동 |

SQLite 로 대체할 수 없습니다. JSONB, `timestamptz`, CHECK 제약을 그대로 검증해야 하기 때문입니다.

---

## 2. 가상환경 + 의존성 설치

```bash
cd bapgyeongchal
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e ".[dev]"
```

설치 확인:

```bash
.venv/bin/pip list | grep -Ei 'fastapi|SQLAlchemy|alembic|psycopg|pydantic|pytest'
```

---

## 3. 환경변수 설정

### 3-1. `.env` 작성

`.env.example` 을 복사해 값을 채웁니다. **`.env` 는 커밋하지 않습니다** (`.gitignore` 처리됨).

```bash
cp .env.example .env
```

필요한 값:

```
POSTGRES_USER=solosafe
POSTGRES_PASSWORD=<로컬 전용 비밀번호>
POSTGRES_DB=solosafe
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

DATABASE_URL=postgresql+psycopg://solosafe:<비밀번호>@localhost:5432/solosafe
TEST_DATABASE_URL=postgresql+psycopg://solosafe:<비밀번호>@localhost:5432/solosafe_test
```

- `TEST_DATABASE_URL` 은 `DATABASE_URL` 과 **반드시 다른 DB** 여야 합니다.
  테스트는 시작할 때 대상 스키마를 초기화하며, 같은 값이면 실행을 거부합니다.
- `DATABASE_URL` 에 기본값을 두지 않았습니다. 잘못된 DB 에 조용히 연결되는 것을 막기 위해서입니다.

---

## 4. PostgreSQL 실행

```bash
docker compose up -d
docker compose ps          # health 상태가 healthy 인지 확인
```

테스트용 DB 를 한 번 만들어 둡니다:

```bash
docker compose exec db psql -U solosafe -d solosafe -c "CREATE DATABASE solosafe_test;"
```

> **주의:** 이 명령들은 아직 실행 검증되지 않았습니다(작성 시점 개발 환경에 Docker 미설치).
> Docker 설치 후 실행해 확인이 필요합니다.

---

## 5. Migration

```bash
.venv/bin/alembic upgrade head          # 스키마 생성
.venv/bin/alembic current                # 현재 리비전 확인
.venv/bin/alembic downgrade base         # 되돌리기
.venv/bin/alembic upgrade head           # 다시 적용
```

DB 없이 생성될 SQL 만 확인하려면(실행 검증 완료):

```bash
.venv/bin/alembic upgrade head --sql
```

---

## 6. 애플리케이션 실행

```bash
.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

확인:

```bash
curl http://127.0.0.1:8000/health        # {"status":"ok"}
curl -i http://127.0.0.1:8000/health/db  # DB 정상: 200 / DB 불가: 503
```

- `/health` 는 DB 를 건드리지 않습니다(앱 자체 생존 확인).
- `/health/db` 는 DB 연결만 확인하며 버전·호스트 등 내부 정보를 노출하지 않습니다.
- DB 가 죽어 있어도 앱은 기동됩니다. 기동 시 연결 실패는 경고 로그로만 남습니다.

---

## 7. 테스트

```bash
.venv/bin/python -m pytest
```

- 테스트는 `TEST_DATABASE_URL` 의 **스키마를 초기화한 뒤 alembic migration 으로 재생성**합니다.
  즉 테스트가 migration 자체도 함께 검증합니다.
- 각 테스트는 트랜잭션 안에서 실행되고 끝나면 rollback 되어 서로 간섭하지 않습니다.

---

## 8. 프로젝트 구조

```
changUp/
├─ app/
│  ├─ main.py                    FastAPI 앱
│  ├─ core/config.py             환경변수 설정 (secret 은 코드에 두지 않음)
│  ├─ core/enums.py              상태/행동 enum (분리 원칙)
│  ├─ db/base.py                 Declarative Base, 공통 Mixin, soft delete 헬퍼
│  ├─ db/session.py              엔진/세션, DB 연결 확인
│  ├─ models/                    User, Product, InventoryItem,
│  │                             InventoryItemEvent, Recommendation, UserAction
│  ├─ schemas/health.py          응답 스키마
│  └─ api/routes/health.py       /health, /health/db
├─ alembic/versions/0001_initial_schema.py
├─ tests/
├─ docs/                         감사·설계 문서 (수정하지 않음)
├─ docker-compose.yml            로컬 PostgreSQL 전용
└─ .env.example
```

`repositories/`, `services/` 계층은 아직 만들지 않았습니다. Step 1 에는 담을 비즈니스 로직이
없어서, 지금 만들면 빈 껍데기만 늘어나기 때문입니다. Step 2(등록/조회) 에서 필요해질 때 추가합니다.

---

## 9. 보안

- 비밀번호·API key 를 코드나 문서에 적지 않습니다. 전부 `.env`(git 제외) 또는 환경변수로 읽습니다.
- `alembic.ini` 에 `sqlalchemy.url` 을 적지 않고 `alembic/env.py` 가 환경변수를 읽습니다.
- `docker-compose.yml` 은 값을 직접 쓰지 않고 `${...}` 로 주입받습니다.
