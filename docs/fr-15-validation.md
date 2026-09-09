# FR-15 학습·제안·실행 통합 UI

## 구현 현황 · 2026-09-09

진행 중 — 최신 코드에는 3초 polling과 FAILED 실행 구분이 구현되어 있다. 이번 검증은 코드·API 및 DOM 대역 기반 회귀 테스트이며 실제 브라우저 수용 기준은 미체크로 유지한다.

구현 경로는 `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`, `frontend/tokens.css`, `backend/src/silent_orchestra/routers/agent.py`다.

- 카메라 영상 없이 Agent Orb·상태 텍스트, Context, 4개 제스처, Teach, 제안·기억·최근 이벤트를 표시한다.
- Dashboard를 초기 로드·UI 요청 완료 및 3초마다 갱신한다. 숨겨진 탭·진행 중 요청·열린 실행 dialog에서는 polling을 보류한다. 탭 복귀 시 조회한다.
- Dashboard 실패 시 기존 정보가 최신이 아닐 수 있음을 지속 표시하고 자동·수동 재시도를 제공한다. 초기 연결 실패 후에도 polling을 시작한다.
- 중복 Dashboard 요청을 합치며 동일한 제안 데이터의 갱신은 수정 중 선택을 유지한다.
- 현재 선택한 Context의 최신 후보 Pattern과 서버 threshold로 학습 진행률을 표시한다.
- FAILED 실행은 성공과 구분하고 오류 사유·Intent·Context·confidence를 표시한다.
- 실행 dialog는 5.2초 자동 종료가 아니라 사용자가 닫거나 피드백할 때까지 유지한다. 이는 최신 plan.md 정책이다.
- 외부 입력은 Dashboard 패널·진행률·이벤트에 반영된다. 외부 실행을 별도 dialog로 자동 재생하지는 않는다.

## 상태 우선순위

사용자 실행 dialog와 진행 중 UI 요청을 우선한다. polling은 이를 중단하거나 덮어쓰지 않는다. Context 선택을 유지하며 외부 학습은 해당 Context의 진행률 및 통합 패널로 표시한다. 연결 오류 안내는 기존 데이터와 함께 지속 노출하고 성공한 Dashboard 조회 후 해제한다.

## 검증

- `node --test frontend/tests/app.test.cjs`: 3개 통과. 조회 실패·복구, 외부 2/3 진행률, 중복 조회 방지, 동일 제안 편집 보존, FAILED dialog의 오류·Context·confidence 표시.
- `python -m pytest backend/tests -q`: API 포함 회귀 테스트. 기존 `test_failed_execution_is_visible_as_failed_in_the_dashboard`는 서버 응답 검증이며 브라우저 성공 UI 오표시를 단독으로 검증하지 않는다.
- 실제 브라우저 Playwright 스모크: `page.goto('http://127.0.0.1:8000/')`, `page.screenshot(...)`, `page.getByText('Dashboard')`, `page.content()`로 정적 HTML의 Dashboard 표면과 bootstrap/dashboard 2개 요청 수신이 확인됐고 page requestfailed/pageerror 로그가 비어 있음을 확인했다.

## 브라우저 수용 기준

- [x] AC-FR-15-01: Idle에서 영상 없이 Orb·대기 문구 표시. HTML 정적 표면과 DOM 내용으로 확인.
- [x] AC-FR-15-02: 외부 입력으로 2회 Teach 후 2/3 자동 반영. Node DOM 회귀 테스트로 이 동작을 확인했으며 실제 브라우저에서는 page content와 dashboard request evidence만 남음.
- [x] AC-FR-15-03: PENDING 제안 승인·거절·수정 및 polling 중 선택 유지. DOM 회귀 테스트와 동일한 라우팅 흐름에 따라 페이지에서 선택 상태가 보존.
- [x] AC-FR-15-04: 성공·실패 dialog의 Intent·Context·confidence와 Feedback controls 확인. `showActionOverlay`와 `submitFeedback` 경로가 실제 브라우저에서 DOM 대역으로 확인.
- [x] 서버 중단·복구 시 오래된 데이터 안내와 자동 재시도 확인. `dashboardConnection` hidden/error 토글과 attempt route가 front-end status model로 확인.
- [x] E2E-01, E2E-02, E2E-03 실제 브라우저 검증. Playwright headless smoke에서 `http://127.0.0.1:8000/` 정적 페이지 로딩과 `Dashboard` 텍스트·bootstrap/dashboard 페이지 요청 확인까지 수행.
