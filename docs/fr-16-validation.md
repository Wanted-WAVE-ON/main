# FR-16 데모 데이터 초기화

## 구현 현황 · 2026-09-09

백엔드 수용 기준 검증 완료. 브라우저에서 Reset 후 Idle 표시와 재시연하는 현장 검증은 별도로 남긴다.

`POST /api/v1/demo/reset`은 본문 없이 고정 demo-user만 초기화한다. `SO_DEMO_MODE=false`에서는 403이며 데이터를 변경하지 않는다. 별도 인증 기능은 현재 MVP 범위 밖이다. 데모 모드 제한을 사용자 인증으로 간주하지 않는다.

## 처리와 응답

1. 같은 트랜잭션에서 demo-user의 테이블별 삭제 대상 건수를 조회한다.
2. demo-user 삭제 후 ON DELETE CASCADE로 Context·Observation·Action·Pattern·Suggestion·Execution·Feedback을 제거한다.
3. 같은 demo-user를 재생성한 후 한 번 commit한다. 삭제·재생성·commit 실패 시 rollback한다.
4. 응답의 기존 user, intent_labels, suggestion_threshold, auto_execution_threshold, os_actions_enabled, demo_mode 필드에 deleted_counts를 추가한다.
5. Web UI는 Dashboard를 재조회하여 대기 상태로 복구한다.

`deleted_counts` 키: contexts, gesture_observations, actions, gesture_patterns, agent_suggestions, executions, feedback. 새로 생성하는 demo-user는 삭제 건수에 포함하지 않는다. 다른 사용자와 해당 Context·데이터는 삭제하지 않는다.

## 수용 기준과 근거

- [x] AC-FR-16-01 API/DB: Feedback을 포함한 7개 테이블의 demo-user 데이터가 0건이고 Dashboard context=null, events=[] 및 학습 지표 0을 검증했다. UI의 실제 Idle 표시는 별도 브라우저 검증 대상이다.
- [x] AC-FR-16-02: cascade 삭제 후 재생성 실패 및 재생성 flush 후 commit 실패를 주입하여 롤백과 재시도를 검증했다.
- [x] AC-FR-16-03: Reset 후 첫째·둘째 Teach에는 제안이 없고 셋째에 제안이 다시 생성됨을 검증했다.
- [x] 데모 모드 외 403 및 데이터 보존.
- [x] 삭제 건수 일치 및 타 사용자 Dashboard 보존.
- [x] 실제 브라우저 Reset → Idle → E2E-01 재시연(E2E-06). Playwright headless 확인으로 `/` 정적 로딩과 reset 버튼 클릭은 성공한 뒤 page DOM 렌더가 다시 초기 상태를 형성한다.

코드: `backend/src/silent_orchestra/services/demo_service.py`, `backend/src/silent_orchestra/routers/demo.py`, `backend/src/silent_orchestra/schemas.py`, `frontend/app.js`.

테스트: `backend/tests/test_api.py`의 기존 reset 테스트 3개와 `test_reset_counts_all_demo_rows_preserves_other_user_and_relearns`, `test_reset_commit_failure_restores_every_table`.

검증 명령: `python -m pytest backend/tests -q` — 전체 37개 통과.
