# SilentOrchestra 2.0 — SPEC

이 문서는 구현이 지켜야 하는 **규범적 규칙**만 담습니다. 충돌 시 이 문서가 우선합니다.
배경은 [docs/brief.md](docs/brief.md), 구조는 [docs/architecture.md](docs/architecture.md),
테이블은 [docs/erd.md](docs/erd.md), 요청·응답 스키마는 실행 중인 서버의 `/docs`(OpenAPI)를 따릅니다.

FR ID(FR-01~FR-17)와 용어는 Notion [WAVE:ON](https://ken-jeong.notion.site/wave-on) 보드와 같은 체계이며,
8장에 FR ↔ 규칙 ↔ 코드 ↔ 테스트 추적표가 있습니다.

## 1. 정의

정해진 제스처를 인식하는 시스템이 아니라, 사용자의 반복 행동과 맥락을 관찰해 개인의 몸짓 언어를
학습하는 로컬 우선 Spatial AI Agent.

```text
Observation → Pattern → Suggestion → Memory → Execution → Feedback
```

기억의 기본 키는 `user + gesture_key + context_scope = intent`입니다. 제스처 자체는 명령이 아닙니다.

### 1.1. 용어

| 용어 | 정의 |
|---|---|
| Gesture | 순간적인 모션 입력. `gesture_key`는 `motion_type:direction`(예: `swipe:right`) |
| Context | 몸짓 발생 시점의 앱·활동·공간·기기 상태. 학습·추론 단위는 `activity`(= `context_scope`) |
| Intent | Gesture와 Context가 결합되어 추론되는 의도(예: `NEXT_SLIDE`) |
| Pattern | 동일 사용자·Gesture·Context에서 반복 관찰된 Gesture-Action 연관 관계 |
| Confidence | Pattern의 신뢰도. 0.0~1.0 |
| Personal Gesture Memory | 승인되어 `ACTIVE`가 된 개인별 Gesture-Intent 기억 |
| Suggestion | 반복 패턴 발견 시 기억 여부를 묻는 Agent의 제안 |
| DRY_RUN | 실제 OS 제어 없이 실행 결과만 표시하는 기본 안전 모드 |

## 2. 범위

| 포함 | 제외 |
|---|---|
| `presentation`, `music` 두 맥락 | 공간 자동 인식, IoT 실기기 |
| UI 제스처 4종: `swipe:right`, `swipe:left`, `open_palm`, `circle` (인코더는 `pinch`, `hold`도 지원) | 얼굴·생체 인식, 클라우드 영상 |
| 3회 반복 → 제안 → 승인 → 자동 실행 | LLM 기반 자유 형식 Intent 생성 |
| 피드백 기반 confidence 갱신 | 인증·결제·다중 사용자 동기화 |
| 선택적 OpenCV Optical Flow 입력 | 완전한 수어 인식 |

학습·실행 가능한 Intent는 맥락별 카탈로그(`services/action_catalog.py`의 `CONTEXT_INTENTS`)로 닫혀 있습니다.
L-2, M-3, F-3의 검증 대상이 이 표입니다.

| Context | 허용 Intent |
|---|---|
| `presentation` | `NEXT_SLIDE`, `PREVIOUS_SLIDE`, `START_PRESENTATION`, `END_PRESENTATION`, `ZOOM_IN`, `ZOOM_OUT` |
| `music` | `NEXT_TRACK`, `PREVIOUS_TRACK`, `TOGGLE_PLAYBACK`, `VOLUME_UP`, `VOLUME_DOWN` |

맥락이나 Intent를 늘리려면 이 카탈로그와 `contexts.activity` / `gesture_patterns.context_scope`의
CHECK 제약을 함께 고쳐야 합니다.

## 3. 도메인 규칙

### 3.1. 개인정보 (타협 불가)

| ID | 규칙 |
|---|---|
| P-1 | 원본 프레임을 DB·파일·네트워크 어디에도 저장하지 않는다. `gesture_observations.frame_stored`는 CHECK 제약으로 항상 `0`이다. |
| P-2 | 요청 스키마는 정의되지 않은 필드를 거부한다(`extra="forbid"`). 이미지·프레임 필드를 보낼 경로가 존재하지 않는다. |
| P-3 | 얼굴·신원 특징을 저장하지 않는다. 저장 대상은 motion_type, direction, duration_ms, embedding, context, 후속 행동뿐이다. |
| P-4 | 웹캠 클라이언트는 프레임을 메모리에서만 사용하고 디스크에 쓰지 않는다. |

### 3.2. 학습

| ID | 규칙 |
|---|---|
| L-1 | 후속 행동은 `POST /teach`로 관찰과 1:1 연결된다. 이미 행동이 연결된 관찰은 400으로 거부한다. |
| L-2 | `action_type`은 해당 맥락의 카탈로그(`CONTEXT_INTENTS`) 안에 있어야 한다. 밖이면 400이며 데이터를 생성하지 않는다. |
| L-3 | 패턴 승격 대상은 동일 `user + gesture_key + activity` 안에서 **최빈 후속 행동 1개**다. |
| L-4 | confidence = `min(0.99, 0.35 + 0.10 × min(승자횟수, 5) + 0.22 × 승자횟수/전체횟수)` |
| L-5 | 최빈 행동이 동률이면 그 gesture+context의 `ACTIVE` 기억을 `CANDIDATE`로 강등하고 `auto_execute`를 끄며, 대기 중 제안을 삭제한다. |
| L-6 | 승자 횟수가 `suggestion_threshold`(기본 3) 이상이고 동률이 아니며 패턴이 `ACTIVE`가 아닐 때만 `PENDING` 제안을 만든다. 같은 패턴에 대기 중 제안이 이미 있으면 새로 만들지 않는다. |
| L-7 | `(user_id, gesture_key, context_scope, intent)`는 유일하다. |

### 3.3. 승인과 기억

| ID | 규칙 |
|---|---|
| M-1 | **승인 전 자동 실행은 0회다.** `status='ACTIVE'`이고 `auto_execute=true`인 기억만 실행 후보가 된다. |
| M-2 | `PENDING` 제안만 응답할 수 있다. 결정은 `ACCEPTED` / `MODIFIED` / `REJECTED`. |
| M-3 | `MODIFIED`는 `modified_intent`가 필수이며, 맥락 카탈로그 안이어야 하고 같은 gesture+context의 다른 기억과 중복될 수 없다. |
| M-4 | 승인 시 confidence를 `auto_execution_threshold` 이상으로 올리고, **같은 gesture+context의 다른 `ACTIVE` 기억은 모두 `CANDIDATE`로 강등한다.** 한 gesture+context당 자동 실행 기억은 최대 1개다. |
| M-5 | 거절 시 패턴은 `REJECTED`, `auto_execute=false`, confidence −0.20. 이후 같은 조합이 다시 관찰되면 `CANDIDATE`로 복귀한다. |
| M-6 | `GET /memories`는 `ACTIVE`이고 confidence ≥ `auto_execution_threshold`인 기억만 반환한다. |

### 3.4. 추론과 실행

| ID | 규칙 |
|---|---|
| I-1 | 후보는 같은 사용자·같은 `context_scope`의 `ACTIVE` + `auto_execute` 기억으로 한정한다. |
| I-2 | 점수 = `pattern.confidence × (0.75 × gesture_key 일치 + 0.25 × max(코사인 유사도, 0))`. gesture_key가 다르면 점수는 confidence의 25%를 넘지 못해 사실상 실행되지 않는다. |
| I-3 | 점수가 `auto_execution_threshold`(기본 0.60) 미만이면 실행하지 않고 사유를 반환한다. |
| I-4 | 실행은 성공·실패와 무관하게 `executions`에 감사 로그로 남는다. 상태는 `SIMULATED` / `SUCCEEDED` / `FAILED`. |
| I-5 | 기본 실행 모드는 `DRY_RUN`이다. `SO_ENABLE_OS_ACTIONS=true`일 때만 실제 키를 보낸다. |
| I-6 | OS 실행 시 `SO_REQUIRE_ACTIVE_WINDOW=true`(기본)면 대상 앱이 활성 창인지 먼저 확인한다. 대상이 아니거나 확인할 수 없으면 **키를 보내지 않고** `FAILED`로 기록하며 사유를 UI에 표시한다. |
| I-7 | 매핑되지 않은 intent는 키를 보내지 않고 `FAILED`로 기록한다. |

### 3.5. 피드백

| ID | 규칙 |
|---|---|
| F-1 | 한 실행당 피드백은 1건이다. 중복은 400. |
| F-2 | confidence 증감: `CORRECT` +0.03, `WRONG_ACTION` −0.15, `ACCIDENTAL_GESTURE` −0.10, `IGNORE` −0.05. 범위는 0.0–0.99. |
| F-3 | `WRONG_ACTION` + `corrected_intent`는 기억의 intent를 교정한다. 교정 intent도 M-3과 동일한 검증을 받는다. |
| F-4 | confidence가 `auto_execution_threshold` 미만으로 떨어지면 `auto_execute=false`, `status='CANDIDATE'`로 강등한다. |

### 3.6. 데모 운영

| ID | 규칙 |
|---|---|
| D-1 | `POST /demo/reset`은 demo-user 삭제와 재생성을 **하나의 트랜잭션**에서 수행한다. 실패 시 이전 상태로 롤백한다. |
| D-2 | 종속 데이터는 `ON DELETE CASCADE`로 함께 삭제된다. 초기화 후 종속 행은 0건이며 재학습이 가능해야 한다. |
| D-3 | `SO_DEMO_MODE=false`면 초기화는 `403`이며 데이터를 변경하지 않는다. |

### 3.7. UI 표시 (FR-15)

| ID | 규칙 |
|---|---|
| U-1 | 카메라 영상을 화면에 노출하지 않는다. 인식 상태는 Agent Orb와 상태 텍스트로만 전달한다. |
| U-2 | 명령 매핑 설정 화면을 전면에 두지 않는다. 화면의 주어는 "AI가 나에 대해 무엇을 배웠는가"이며, 기억은 Gesture·Context·Intent·confidence로 표시한다. |
| U-3 | 실행 결과 오버레이는 사용자를 막지 않는다. 실패한 실행은 성공과 구분해 사유와 함께 표시한다. |

UI는 다음 7개 상태를 모두 표현해야 한다.
| 상태 | 표시 |
|---|---|
| Idle | 공간을 이해하고 있는 대기 |
| Listening | 모션 특징과 Context 분석 중 |
| Observation ready | 몸짓 직후 후속 행동 선택 대기 |
| Learning progress | 1/3 → 2/3 → 3/3 |
| Suggestion pending | 승인·거절 대기 |
| Execution overlay | 실행된 Intent와 confidence |
| Feedback | 맞아요 / 아니에요 |

외부 입력(웹캠 클라이언트 등)으로 바뀐 상태는 UI가 주기적으로 자동 갱신한다.

## 4. 상태 전이

```text
GesturePattern
  CANDIDATE ──승인/수정──▶ ACTIVE ──동률 관찰/저confidence 피드백──▶ CANDIDATE
      └───────거절───────▶ REJECTED ──재관찰──▶ CANDIDATE

AgentSuggestion
  PENDING ──▶ ACCEPTED | MODIFIED | REJECTED   (재전이 없음)
  PENDING ──동률 관찰──▶ 삭제
```

## 5. 데이터 계약

`users`, `contexts`, `gesture_observations`, `actions`, `gesture_patterns`, `agent_suggestions`,
`executions`, `feedback`. 상세 컬럼은 [docs/erd.md](docs/erd.md)와 [sql/schema.sql](sql/schema.sql).

- 관찰 1건마다 `contexts` 행이 1건 생성된다(관찰 시점 스냅샷).
- `actions.observation_id`는 유일하다(L-1).
- `feedback.execution_id`는 유일하다(F-1).
- `activity`와 `context_scope`는 `presentation` / `music`만 허용하는 CHECK 제약을 가진다.

## 6. 설정

| 변수 | 기본값 | 의미 |
|---|---|---|
| `SO_SUGGESTION_THRESHOLD` | `3` | 제안이 뜨는 반복 횟수(L-6) |
| `SO_AUTO_EXECUTION_THRESHOLD` | `0.60` | 자동 실행 최소 confidence(I-3) |
| `SO_ENABLE_OS_ACTIONS` | `false` | 실제 키 입력 허용(I-5) |
| `SO_REQUIRE_ACTIVE_WINDOW` | `true` | 활성 창 검증(I-6) |
| `SO_DEMO_MODE` | `true` | 데모 초기화 허용(D-3) |
| `SO_DATABASE_URL` | 로컬 SQLite | 저장소 |
| `SO_ALLOWED_ORIGINS` | 로컬 2개 | CORS 허용 출처 |

## 7. 수용 기준

| 기준 | 목표 | 검증 |
|---|---|---|
| 원본 프레임 저장 | 0건 | `test_observation_never_accepts_or_returns_raw_frame`, CHECK `ck_raw_frame_never_stored` |
| 승인 전 자동 실행 | 0회 | `test_learning_loop_suggest_accept_execute` |
| 맥락 분기 | 데모 시나리오 100% | `test_same_gesture_changes_with_context` |
| 비활성 창 키 입력 차단 | 100% | `test_os_execution_is_blocked_when_target_app_is_not_active` |
| 초기화 원자성 | 종속 데이터 0건 + 재학습 성공 | `test_reset_clears_learned_data_and_relearning_works` |
| 핵심 테스트 | 전부 통과 | `python -m pytest -q` → 20 passed |
| SQL 계약 | 전부 통과 | `scripts/validate_sqlite.py` → 38 statements |
| 핵심 루프 데모 | 90초 이내 | [README.md](README.md#90초-데모)의 7단계 |
| 발표 대본 | 3분 이내 | [docs/demo-script.md](docs/demo-script.md) 리허설 |

## 8. 기능 요구사항 추적

Notion 보드의 FR ID를 이 문서의 규칙, 구현, 테스트에 연결합니다. FR-01~FR-15는 필수, FR-16~FR-17은 선택입니다.

| FR | 기능 | 규칙 | 구현 | 상태 |
|---|---|---|---|---|
| FR-01 | 모션 입력 감지 | P-1, P-2 | `services/gesture_encoder.py`, `POST /observe` | 완료 |
| FR-02 | Context 관리 | 2장, `ck_context_activity` | `routers/agent.py` | 완료 |
| FR-03 | Observation 기록 | P-1, I-1 | `POST /observe` | 완료 |
| FR-04 | 후속 행동 연결(Teach) | L-1, L-2 | `services/pattern_learning.py` | 완료 |
| FR-05 | Pattern Learning | L-3, L-4, L-7 | `pattern_learning._confidence` | 완료 |
| FR-06 | Intent Reasoning | I-1, I-2, I-3 | `services/intent_reasoner.py` | 완료 |
| FR-07 | Suggestion 생성 | L-5, L-6 | `pattern_learning.record_user_action` | 완료 |
| FR-08 | Suggestion 응답 처리 | M-2, M-3, M-4, M-5 | `pattern_learning.respond_to_suggestion` | 완료 |
| FR-09 | Personal Memory 조회 | M-6 | `GET /memories` | 완료 |
| FR-10 | 자동 실행 | I-3, I-5, I-6, I-7 | `services/action_executor.py` | 완료 |
| FR-11 | Execution Audit | I-4 | `models.Execution` | 완료 |
| FR-12 | Feedback 처리 | F-1, F-2, F-3 | `services/feedback_service.py` | 완료 |
| FR-13 | 상태 자동 강등 | F-4 | `feedback_service.record_feedback` | 완료 |
| FR-14 | Privacy 보장 | P-1~P-4 | `ck_raw_frame_never_stored`, `GET /demo/privacy` | 완료 |
| FR-15 | 대시보드 상태 제공 | U-1, U-2, U-3 | `GET /dashboard`, `static/app.js` | 완료 |
| FR-16 | Demo Reset | D-1, D-2, D-3 | `services/demo_service.py` | 완료 |
| FR-17 | 실시간 웹캠 입력 | P-4 | `scripts/webcam_gesture_client.py` | 검증 중 |

FR-17만 미완료입니다. 감지 로직은 구현되어 있고 하드웨어(조명·배경·프레임률) 품질 검증이 남았습니다.
