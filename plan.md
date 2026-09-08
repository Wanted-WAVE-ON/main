# PLAN — SilentOrchestra 2.0

## 구현 방향

- 루트의 `backend/`에 Python 패키지·테스트·SQL·스크립트를, `frontend/`에 HTML·CSS·JS를 둔다. FastAPI가 프론트 정적 파일을 제공하며 별도 빌드 도구는 사용하지 않는다. 공통 문서·`.env`·`data/`와 실행 진입점 `run_demo.py`는 루트에 유지한다.

- FastAPI(도메인 엔드포인트 8개 + demo/health), 단일 페이지 워크벤치, 로컬 SQLite를 사용한다. 구조·코드 지도는 [architecture](docs/architecture.md), 설정은 [config.py](backend/src/silent_orchestra/config.py)(`SO_DATABASE_URL` 기본 로컬 SQLite, `SO_ALLOWED_ORIGINS` 기본 로컬 2개).
- 기본 시연은 버튼 기반 Stable Simulation + DRY_RUN. 기능 추가보다 정합성·검증을 우선한다.
- 의도적 단순화: [app.js](frontend/app.js)는 SSE 대신 3초 폴링, 실행 오버레이 자동 닫힘 없음; [action_executor.py](backend/src/silent_orchestra/services/action_executor.py)는 활성 창 이름 부분 문자열 매칭·리눅스 활성 창 미지원; [models.py](backend/src/silent_orchestra/models.py)의 `Annotated` 컬럼 별칭은 유지한다.

## 단계별 계획

1. 발표자가 [대본](docs/demo-script.md)을 소리 내어 읽으며 타이밍을 측정한다. UI 조작 외 내레이션은 사람의 리허설로 검증한다.
2. 선택 경로를 시연할 때만 [운영 가이드](docs/operations.md)에 따라 발표 PC의 OS 실행을 확인하거나 웹캠 인식 품질을 확인한다.
3. 조건을 충족할 때만 확장한다.

| 확장 | 착수 조건 / 로드맵 |
|---|---|
| 동적 학습 임계값 | 실사용 로그로 오작동 비용 측정 가능 |
| 학습형 embedding·유사도 | 개인 편차에서 단순 코사인 오분류 발생 / V1 |
| browser·kitchen 등 맥락 추가 | 두 맥락 데모 검증 후, SPEC의 카탈로그·CHECK 변경 준수 / V2 |
| LLM Intent, 인증·다중 사용자 | 규칙 카탈로그로 요구 표현 불가, 또는 demo-user 단일 사용자 전제 변경 / V3 |
| SSE·WebSocket | 사용자·탭 증가로 3초 폴링 부족 |
| PostgreSQL | 단일 PC 데모 범위 초과 |
| 오버레이 자동 닫힘 | 데모에서 상시 사용으로 전환 |
| 활성 창 판정 고도화 | 앱 이름 중복 오탐 또는 리눅스 OS 실행 필요 |

## 검증 전략

- [test_api.py](backend/tests/test_api.py)의 프레임 거부, 학습→승인→실행, 맥락 분기, 비활성 창 차단, 초기화→재학습 테스트로 [완료 기준](spec.md#완료-기준)을 확인한다.
- [README 테스트](README.md#테스트)의 명령으로 [CI](.github/workflows/ci.yml)와 같은 검증을 수행하고, 결과는 TASKS에 기록한다.

- 초기화 후 [발표 대본](docs/demo-script.md)의 조작·내레이션을 리허설한다.

## 리스크 및 미결정

- 웹캠 품질은 조명·배경·프레임률에 좌우된다. 기본 시뮬레이션 경로를 유지한다.
- OS 실행은 발표 PC의 권한·활성 창 확인 지원에 좌우된다. 환경별 제약과 대응은 [운영 가이드](docs/operations.md#권한과-활성-창-확인)에서 관리한다.
- 단순 embedding의 개인 편차 한계는 SPEC I-2의 키 일치 가중치로, 같은 맥락의 행동 경쟁은 L-5의 자동 실행 중단·제안 철회로 억제한다.
