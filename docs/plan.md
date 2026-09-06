# SilentOrchestra 2.0 작업 계획

명세는 [SPEC.md](../SPEC.md). 이 문서는 **지금 상태와 남은 일**만 다룹니다.
FR-01~FR-17 구현 현황의 원본은 Notion [WAVE:ON](https://ken-jeong.notion.site/wave-on)의 `기능 명세` 표입니다.

## 1. 현재 상태

2026-09-05 기준 실제 측정값입니다.

| 항목 | 상태 |
|---|---|
| Pytest | 20 passed |
| SQLite 검증 | 38 statements passed |
| CI | `pytest` + `validate_sqlite.py` (`.github/workflows/ci.yml`) |
| 백엔드 | FastAPI 8개 도메인 엔드포인트 + demo/health |
| 프론트 | 단일 페이지 워크벤치(`static/`), 3초 폴링 |
| 기능 요구사항 | FR-01~FR-16 완료, FR-17(웹캠) 검증 중 |

기능 구현은 SPEC 3장 전체를 충족합니다. 남은 일은 **정합성 정리와 검증**이지 기능 추가가 아닙니다.

## 2. 남은 작업

### P0 — 제출 전 반드시

| # | 작업 | 근거 |
|---|---|---|
| 1 | `POST /demo/reset` 후 [docs/demo-script.md](demo-script.md) 순서로 3분 리허설 1회 | 수용 기준의 시간 항목만 자동 검증 불가 |
| 2 | Notion `기획서`·`기능 정의서`의 테스트 수치를 `5 passed` → `20 passed`로 갱신 | 저장소 문서는 동기화 완료. 심사 중 수치 불일치는 신뢰도 손실 |

### P1 — 선택 경로를 실제로 시연할 경우에만

기본 데모 경로(DRY_RUN + 버튼 시뮬레이션)로 간다면 P1은 전부 불필요합니다.

| # | 작업 | 조건 | 근거 |
|---|---|---|---|
| 3 | 발표 PC에서 `SO_ENABLE_OS_ACTIONS=true` + `pyautogui` + 접근성 권한 확인 | 실제 OS 실행 | 권한 없으면 I-6에 따라 전부 `FAILED` |
| 4 | 실제 사용할 앱 이름을 `action_executor.py`의 `TARGET_WINDOWS`에 추가 | 실제 OS 실행 | 검증을 끄는 것은 최후 수단 |
| 5 | 발표 환경의 조명·배경·프레임률에서 좌우 swipe 감지 품질 확인 후 Notion FR-17 갱신 | 웹캠(FR-17) | 코드는 있고 하드웨어 검증만 남음 |

### P2 — 지금 만들지 않기로 한 것

| 항목 | 착수 조건 | 로드맵 |
|---|---|---|
| 동적 학습 임계값(3회 → 맥락별 조정) | 실사용 로그로 오작동 비용을 측정할 수 있을 때 | — |
| 학습형 embedding / 유사도 모델 | 단순 코사인 유사도가 개인 편차에서 오분류를 낼 때 | V1 |
| 맥락 추가(browser, kitchen 등) | 두 맥락 데모가 검증된 후. CHECK 제약과 카탈로그를 함께 수정 | V2 |
| LLM 기반 Intent 확장 | 규칙 기반 카탈로그로 표현 못 하는 요구가 생길 때 | V3 |
| 인증·다중 사용자 | demo-user 단일 사용자 전제를 깰 때 | V3 |
| SSE·WebSocket 실시간 갱신 | 3초 폴링이 다중 탭·다중 사용자에서 부족해질 때 | — |
| PostgreSQL 이전 | 단일 PC 데모를 벗어날 때 | — |

## 3. 알려진 위험

| 위험 | 영향 | 대응 |
|---|---|---|
| 웹캠 인식 품질이 조명·배경에 좌우됨 | 실시간 데모 실패 | 기본 경로를 버튼 기반 Stable Simulation으로 유지 |
| macOS 접근성 권한 거부 | 활성 창 확인 불가 → 전부 `FAILED` | 기본 `DRY_RUN` 유지, 사유가 UI에 표시됨 |
| X11/Wayland는 활성 창 확인 수단 없음 | 리눅스에서 OS 실행 불가 | 해당 환경에서만 `SO_REQUIRE_ACTIVE_WINDOW=false` |
| MVP embedding이 단순함 | 장기 데이터에서 개인 편차 구분 한계 | gesture_key 일치가 점수의 75%라 오실행은 억제됨(I-2) |
| 같은 Context에서 여러 행동이 경쟁 | 더 정교한 ambiguity handling 필요 | 동률이면 자동 실행 중단 + 제안 철회(L-5) |

## 4. 의도적 단순화 (ponytail 부채)

| 위치 | 단순화 | 승급 조건 |
|---|---|---|
| [static/app.js:420](../src/silent_orchestra/static/app.js:420) | SSE 대신 3초 폴링 | 사용자·탭이 늘어날 때 |
| [action_executor.py:22](../src/silent_orchestra/services/action_executor.py:22) | 활성 창 이름 부분 문자열 매칭 | 앱 이름이 겹쳐 오탐이 날 때 |
| [action_executor.py:57](../src/silent_orchestra/services/action_executor.py:57) | 리눅스 활성 창 미지원 | 리눅스에서 OS 실행이 필요할 때 |
| [models.py:23](../src/silent_orchestra/models.py:23) | `Annotated` 컬럼 별칭 | 없음(유지) |

## 5. 검증

```bash
python -m pytest -q
```

```bash
python scripts/validate_sqlite.py --schema sql/schema.sql --seed sql/seed.sql --queries sql/queries.sql --tests sql/tests.sql --report sql/validation-report.json
```
