# SilentOrchestra 2.0

반복되는 몸짓과 후속 조작을 활동별로 학습하고, 사용자가 승인한 행동 연결을 기억하는 로컬 우선 Spatial AI Agent 데모입니다.

## 기술 스택

Python · FastAPI · SQLAlchemy · SQLite · HTML / CSS / JavaScript

선택 기능으로 OpenCV 웹캠 입력과 PyAutoGUI OS 제어를 사용합니다. 의존성은 [pyproject.toml](backend/pyproject.toml)에서 관리합니다.

## 시작하기

### 사전 요구사항

- Python 3.11 이상
- 웹 브라우저

### 설치 및 실행

저장소 루트에서 실행합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ./backend
python run_demo.py
```

Windows에서는 가상환경 활성화에 `.venv\Scripts\Activate.ps1`을 사용합니다.
브라우저에서 [로컬 데모](http://127.0.0.1:8000)를 엽니다.

## 사용 방법

### 데모

화면의 `Presentation` 맥락과 버튼 입력으로 시작합니다. 웹 UI는 몸짓·맥락·행동을 직접 고르는 라벨 시뮬레이션입니다. 기본 `DRY_RUN` 모드에서는 실제 키 입력 없이 실행 결과를 표시합니다.
시연 순서와 실패 시 대체 흐름은 [데모 대본](docs/demo-script.md)을 따릅니다.

API를 직접 호출하려면 실행 중인 서버의 [Swagger UI](http://127.0.0.1:8000/docs)를 사용합니다.

### 웹캠 입력

좌우 swipe의 실측 특징을 전송합니다. Windows에서는 활성 앱의 맥락과 실제 후속 키 조작을 관측하고, 다른 플랫폼에서는 명시적 라벨 모드를 사용합니다. 설치·학습 모드·허용 키·한계는 [운영 가이드](docs/operations.md#웹캠-학습과-실제-조작-관측), 현장 확인 상태는 [FR-17 검증 기록](docs/fr-17-validation.md)을 참고합니다.

### 실제 OS 키 입력

실제 앱 제어를 시연할 때는 [운영 가이드](docs/operations.md)의 설치·설정·활성 창 확인 절차를 따릅니다.

## 테스트

```bash
python -m pip install -e "./backend[dev]"
python -m pytest backend/tests -q
python backend/scripts/validate_sqlite.py --schema backend/sql/schema.sql --seed backend/sql/seed.sql --queries backend/sql/queries.sql --tests backend/sql/tests.sql --report backend/sql/validation-report.json
```

자동 검증 설정은 [CI 워크플로](.github/workflows/ci.yml), 실행 결과는 [작업 현황](tasks.md#검증-기록)에서 관리합니다.

## 관련 문서

| 문서 | 내용 |
| --- | --- |
| [spec.md](spec.md) | 요구사항·개인정보·승인 및 실행 규칙·완료 기준 |
| [plan.md](plan.md) | 구현 방향·검증 전략·제약 및 확장 조건 |
| [tasks.md](tasks.md) | 진행 현황·검증 결과·남은 작업 |
| [프로젝트 브리프](docs/brief.md) | 배경·대상 사용자·핵심 가치 |
| [아키텍처](docs/architecture.md) | 처리 흐름·코드 위치 |
| [데이터 설계](docs/erd.md) | ERD·테이블·SQL 산출물 |
| [디자인](docs/design.md) | UI·시각 디자인 기준 |
| [데모 대본](docs/demo-script.md) | 발표 순서·조작·실패 시 대체 흐름 |
| [운영 가이드](docs/operations.md) | 웹캠 관측·라벨 모드·OS 실행 설정·권한·실패 대응 |
| [Q&A](docs/qna.md) | 예상 질문과 답변 |
| [결정 로그](docs/decision-log.md) | 설계 결정과 근거 |
| [작업 지침](AGENTS.md) | 문서별 역할·변경 원칙 |
