# PLAN — SilentOrchestra 2.0

[SPEC.md](SPEC.md) · [TASKS.md](TASKS.md)

## 구현 방향

- FastAPI(도메인 엔드포인트 8개 + demo/health), 단일 페이지 워크벤치, 로컬 SQLite를 사용한다. 구조·코드 지도는 [architecture](docs/architecture.md), 설정은 [config.py](src/silent_orchestra/config.py)(`SO_DATABASE_URL` 기본 로컬 SQLite, `SO_ALLOWED_ORIGINS` 기본 로컬 2개).
- 기본 시연은 버튼 기반 Stable Simulation + DRY_RUN. 기능 추가보다 정합성·검증을 우선한다.
- 의도적 단순화: [app.js](src/silent_orchestra/static/app.js)는 SSE 대신 3초 폴링, 실행 오버레이 자동 닫힘 없음; [action_executor.py](src/silent_orchestra/services/action_executor.py)는 활성 창 이름 부분 문자열 매칭·리눅스 활성 창 미지원; [models.py](src/silent_orchestra/models.py)의 `Annotated` 컬럼 별칭은 유지한다.

## 단계별 계획

1. 발표자가 [대본](docs/demo-script.md)을 소리 내어 읽으며 타이밍을 측정한다. UI 조작 외 내레이션은 사람의 리허설로 검증한다.
2. 선택 경로를 시연할 때만 발표 PC의 OS 실행 권한·앱 매핑 또는 웹캠 인식 품질을 확인한다.
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

- [test_api.py](tests/test_api.py)의 프레임 거부, 학습→승인→실행, 맥락 분기, 비활성 창 차단, 초기화→재학습 테스트로 [완료 기준](SPEC.md#완료-기준)을 확인한다.
- [CI](.github/workflows/ci.yml)와 동일하게 아래 명령을 실행한다. 실행 결과는 TASKS에 기록한다.

```bash
python -m pytest -q
python scripts/validate_sqlite.py --schema sql/schema.sql --seed sql/seed.sql --queries sql/queries.sql --tests sql/tests.sql --report sql/validation-report.json
```

- 초기화 후 [README 데모](README.md#90초-데모)의 7단계와 [발표 대본](docs/demo-script.md)을 리허설한다.

## 리스크 및 미결정

- 웹캠 품질은 조명·배경·프레임률에 좌우된다. 기본 시뮬레이션 경로를 유지한다.
- macOS 접근성 권한 거부는 활성 창 확인 실패로 이어진다. 기본 DRY_RUN을 유지하며 실패 표시는 SPEC I-6을 따른다.
- X11/Wayland는 활성 창 확인 수단이 없다. 해당 환경에서만 `SO_REQUIRE_ACTIVE_WINDOW=false`를 고려하며, 검증 해제는 최후 수단이다.
- 단순 embedding의 개인 편차 한계는 SPEC I-2의 키 일치 가중치로, 같은 맥락의 행동 경쟁은 L-5의 자동 실행 중단·제안 철회로 억제한다.
