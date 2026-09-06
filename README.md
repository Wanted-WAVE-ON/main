# SilentOrchestra 2.0

사용자가 정해진 제스처를 외우는 대신, AI가 반복되는 몸짓과 현재 맥락을 관찰해 개인의 몸짓 언어를 학습하는
로컬 우선 Spatial AI Agent 데모입니다.

```text
Observation → Pattern → Suggestion → Memory → Execution → Feedback
```

같은 몸짓도 맥락에 따라 다르게 학습됩니다. `presentation + swipe:right → NEXT_SLIDE`,
`music + swipe:right → NEXT_TRACK`. 제스처 자체는 명령이 아니며, 3회 반복 → 제안 → **사용자 승인 이후에만**
자동 실행됩니다.

- 규범적 규칙(구현이 지켜야 하는 계약): [SPEC.md](SPEC.md) — 충돌 시 우선
- 현재 상태와 남은 일: [docs/plan.md](docs/plan.md)
- API 계약: 서버 실행 후 `http://127.0.0.1:8000/docs` (OpenAPI)

## 빠른 실행

```bash
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
python -m pip install -e .
python run_demo.py
```

브라우저에서 `http://127.0.0.1:8000`을 엽니다.

## 90초 데모

1. `Presentation` 맥락에서 `오른쪽 손짓` → 후속 행동 `다음 슬라이드` 선택
2. 같은 과정 총 3회 반복
3. 제안 카드에서 `기억하기`
4. 다시 `오른쪽 손짓` → `다음 슬라이드` 자동 실행
5. `Music`으로 전환해 `다음 트랙`으로 반복 → 맥락 분기 시연

기본값은 `DRY_RUN`이라 실제 키 입력 대신 실행 결과만 표시합니다. 3분 발표 대본은
[docs/demo-script.md](docs/demo-script.md)에 있습니다.

## 선택 기능

### 웹캠 모션 감지 (FR-17)

OpenCV Optical Flow 기반. 원본 프레임은 저장하지 않습니다.

```bash
python -m pip install -e ".[camera]"
python scripts/webcam_gesture_client.py --activity presentation
```

키보드 보조: `N` 다음 / `B` 이전 / `Space` 재생·일시정지 / `Q` 종료.
발표 현장에서는 하드웨어 변수 때문에 버튼 기반 Stable Simulation을 권장합니다.

### 실제 OS 키 입력

```bash
python -m pip install pyautogui
```

```env
SO_ENABLE_OS_ACTIONS=true
```

키 입력 직전에 대상 앱이 활성 창인지 확인하고, 아니면 키를 보내지 않고 `FAILED`로 기록합니다(SPEC I-6).
대상 앱 이름은 `services/action_executor.py`의 `TARGET_WINDOWS`에서 조정합니다. 검증을 끄는
`SO_REQUIRE_ACTIVE_WINDOW=false`는 활성 창 확인 수단이 없는 환경(X11/Wayland)에서만 쓰는 최후 수단입니다.

전체 환경 변수는 [SPEC.md](SPEC.md#6-설정)에 있습니다.

## 검증

```bash
python -m pip install -e ".[dev]" && python -m pytest -q
```

```bash
python scripts/validate_sqlite.py --schema sql/schema.sql --seed sql/seed.sql --queries sql/queries.sql --tests sql/tests.sql --report sql/validation-report.json
```

현재: pytest 20 passed, SQLite 38 statements passed. 수용 기준은 [SPEC.md](SPEC.md#7-수용-기준) 참고.

## 구조

```text
SPEC.md          규범적 규칙(충돌 시 우선)
docs/            기획·아키텍처·ERD·데모 대본·Q&A·결정 로그·현재 상태(plan.md)·디자인 시스템(design.md)
design/          design-tokens.json (구현 토큰: src/silent_orchestra/static/tokens.css)
sql/             schema, seed, queries, tests, 검증 보고서
src/silent_orchestra/  FastAPI 백엔드(routers/ + services/)와 웹 UI(static/)
scripts/         SQLite 검증, 웹캠 모션 클라이언트
tests/           API·DB·웹캠 클라이언트 테스트
assets/          다이어그램 소스(.dot), 브랜드 아이콘
```

## 개인정보 보호

원본 영상 저장·얼굴 인식·클라우드 업로드를 하지 않습니다. 모션 특징 벡터와 맥락만 로컬에 남으며,
DB CHECK 제약으로 강제됩니다. 규칙 전문은 [SPEC.md](SPEC.md#31-개인정보-타협-불가) P-1~P-4.
