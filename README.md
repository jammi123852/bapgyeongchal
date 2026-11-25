# SoloSafe — v0.1

1인 가구가 냉장고에 넣어둔 식품을 잊어 소비기한을 넘기고 버리는 문제를 다루는 서비스입니다.

**현재: v0.1 MUST 6개 구현 완료 (백엔드 Step 1~8 + 모바일 앱 `mobile/`).**
Step 9(2~3명 2주 실사용 검증)는 사람이 진행해야 하는 단계라 아직 하지 않았습니다.
바코드 / 레시피 / 알림 / 회수제품 / 건강 기능은 **구현되어 있지 않습니다.** (사진 → 소비기한 OCR 은 아래 6-1)

| 기능 | API |
|---|---|
| 가입 / 로그인 / 로그아웃 / 내 정보 | `POST /auth/signup`, `POST /auth/login`, `POST /auth/logout`, `GET /me` |
| 음식 등록 · 목록(임박순) · 상세 · 수정 · 삭제(soft) | `POST/GET /inventory`, `GET/PATCH/DELETE /inventory/{id}` |
| 원탭 기록 (다 먹음 / 일부 / 버림 / 기한 지남) | `POST /inventory/{id}/actions` |
| 오늘 먼저 먹을 것 (baseline1 + 이유) + 기록 | `POST /eat-first`, `POST /eat-first/{batch_id}/shown` |

전체 API 문서: 서버 실행 후 http://127.0.0.1:8000/docs

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

### 6-1. OCR 서버 (사진 → 소비기한, 선택)

별도 venv `.venv-ocr` (PaddleOCR + onnxruntime, CPU). 흐름: 날짜 영역 검출(YOLOX-s ONNX) → 크롭 OCR → 회전 재시도 → 전체 사진 OCR.
ONNX 파일(`outputs/roi_det/yolox_s_full_e80/best.onnx`)은 git 에 없으므로 체크포인트에서 한 번 만든다 (`.venv-det`).
파일이 없으면 서버는 전체 사진 OCR 만 한다 (`/health` 의 `roi_model`).

```bash
.venv-det/bin/python scripts/export_roi_onnx.py      # ckpt sha256 확인 후 best.onnx 생성
.venv-ocr/bin/uvicorn ocr_service.server:app --host 127.0.0.1 --port 8001
curl http://127.0.0.1:8001/health
```

백엔드는 `POST /ocr/expiry` 로 이 서버에 넘긴다. 응답의 `stage` = `roi` / `roi_rotate` / `full`.
데이터 출처: ExpDate (Seker & Ahn 2022, CC BY 4.0) https://felizang.github.io/expdate/

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
│  ├─ core/security.py           비밀번호 해시(bcrypt), JWT
│  ├─ schemas/                   요청/응답, feature_snapshot 계약(eat_first.py)
│  ├─ services/                  inventory / actions / eat_first(정렬 규칙) / recommendations(기록)
│  └─ api/routes/                health, auth, inventory, eat_first
├─ alembic/versions/             0001 초기 스키마, 0002 인증, 0003 추천 노출 시각
├─ tests/
├─ mobile/                       Expo(React Native) 앱
├─ docs/                         감사·설계 문서 (수정하지 않음)
├─ docker-compose.yml            로컬 PostgreSQL 전용
└─ .env.example
```

`repositories/` 계층은 두지 않았습니다. 조회가 단순해 service 에서 직접 쿼리합니다.

---

## 8-1. 모바일 앱 실행 (`mobile/`)

```bash
# 1) 백엔드 먼저 (위 6절)
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000

# 2) 앱 — 브라우저로 보기
cd mobile && npm install && npx expo start --web

# 2') 앱 — 내 폰으로 보기 (Expo Go 앱 설치, PC 와 같은 와이파이)
#     localhost 는 폰에서 PC 를 가리키지 않으므로 PC 의 LAN IP 를 넣는다.
EXPO_PUBLIC_API_URL=http://<PC의 LAN IP>:8000 npx expo start
```

- 화면: 로그인/가입 → 홈(오늘 먼저 먹을 것 상위 3개 + 이유, 나머지 목록, 원탭 기록) → 음식 추가
- 음식 추가: 이름 + 소비기한 버튼(오늘/내일/3일 뒤/7일 뒤/모름) 한 번. 개봉·보관은 '더 입력하기' 안에
- 추천은 화면에 그려진 뒤에만 `/shown` 으로 노출 기록된다
- WSL 에서 폰 연결 시 Windows 방화벽/포트 포워딩 설정이 필요할 수 있다 (확인 필요)
- `eas build` 등 EAS 클라우드 빌드는 과금 가능성이 있어 사용하지 않았다

---

## 9. 보안

- 비밀번호·API key 를 코드나 문서에 적지 않습니다. 전부 `.env`(git 제외) 또는 환경변수로 읽습니다.
- `alembic.ini` 에 `sqlalchemy.url` 을 적지 않고 `alembic/env.py` 가 환경변수를 읽습니다.
- `docker-compose.yml` 은 값을 직접 쓰지 않고 `${...}` 로 주입받습니다.
