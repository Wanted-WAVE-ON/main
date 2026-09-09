# SPEC — SilentOrchestra 2.0

## 개요

반복 행동과 맥락에서 개인의 몸짓 언어를 학습하는 로컬 우선 Spatial AI Agent. 흐름은 `Observation → Pattern → Suggestion → Memory → Execution → Feedback`이며, 기억의 키는 `user + gesture_key + context_scope = intent`다. 제스처 자체는 명령이 아니다.

이 문서는 구현의 규범이며 충돌 시 우선한다. 배경은 [brief](docs/brief.md), 용어·FR ID는 [Notion WAVE:ON](https://ken-jeong.notion.site/wave-on)과 맞춘다.

## 범위

- 포함: `presentation`·`music`, UI 제스처 `swipe:right`·`swipe:left`·`open_palm`·`circle`, 반복 학습·제안·승인·실행·피드백. 인코더는 `pinch`·`hold`도 지원한다.
- FR-01~FR-15는 필수, FR-16(데모 초기화)·FR-17(OpenCV Optical Flow 웹캠 입력)은 선택이다.
- 제외: 공간 자동 인식, IoT 실기기, 얼굴·생체 인식, 클라우드 영상, LLM 자유 형식 Intent, 인증·결제·다중 사용자 동기화, 완전한 수어 인식.
- 학습·실행 Intent는 맥락별 [CONTEXT_INTENTS](backend/src/silent_orchestra/services/action_catalog.py)로 제한한다. 맥락 추가 시 카탈로그와 `contexts.activity`·`gesture_patterns.context_scope` CHECK 제약을 함께 변경한다.

## 요구사항

`gesture_key`는 `motion_type:direction`, 학습 맥락은 `activity = context_scope`다. Pattern은 같은 사용자·몸짓·맥락의 반복 행동 연관, Memory는 승인된 `ACTIVE` 패턴, confidence는 0~1 신뢰도다.

### 입력·개인정보 (FR-01, FR-03, FR-14, FR-17)

| ID | 규칙 |
|---|---|
| P-1 | 원본 프레임을 DB·파일·네트워크에 저장하지 않는다. `gesture_observations.frame_stored`는 CHECK로 항상 `0`이다. |
| P-2 | 요청은 미정의 필드를 거부한다(`extra="forbid"`). 이미지·프레임을 전송할 필드는 없다. |
| P-3 | 얼굴·신원 특징을 저장하지 않는다. 저장 대상은 motion_type, direction, duration_ms, embedding, context, 후속 행동뿐이다. |
| P-4 | 웹캠 프레임은 메모리에서만 사용하고 디스크에 쓰지 않는다. |

### 맥락·학습 (FR-02, FR-04, FR-05, FR-07)

| ID | 규칙 |
|---|---|
| L-1 | `POST /teach`는 관찰과 후속 행동을 1:1로 연결한다. 이미 연결된 관찰은 400이다. |
| L-2 | `action_type`이 맥락 카탈로그 밖이면 400이며 데이터를 생성하지 않는다. |
| L-3 | 같은 `user + gesture_key + activity`의 최빈 후속 행동 1개만 승격 대상이다. |
| L-4 | confidence = `min(0.99, 0.35 + 0.10 × min(승자횟수, 5) + 0.22 × 승자횟수/전체횟수)`. |
| L-5 | 최빈 행동 동률이면 해당 gesture+context의 `ACTIVE` 기억을 `CANDIDATE`로 강등하고 `auto_execute`를 끄며 대기 제안을 삭제한다. |
| L-6 | 승자 횟수 ≥ `suggestion_threshold`(기본 3), 동률 아님, 패턴이 `ACTIVE` 아님일 때만 `PENDING` 제안을 만든다. 패턴당 대기 제안은 최대 1개다. |
| L-7 | `(user_id, gesture_key, context_scope, intent)`는 유일하다. |

관찰마다 Context 스냅샷 1행을 생성한다. 테이블·컬럼·제약 원본은 [ERD](docs/erd.md)와 [schema.sql](backend/sql/schema.sql), 요청·응답 스키마는 실행 서버의 `/docs`다.

### 승인·기억 (FR-08, FR-09)

| ID | 규칙 |
|---|---|
| M-1 | 승인 전 자동 실행은 0회다. `ACTIVE` + `auto_execute=true` 기억만 실행 후보가 된다. |
| M-2 | `PENDING`만 `ACCEPTED`·`MODIFIED`·`REJECTED`로 응답할 수 있고 재전이는 없다. |
| M-3 | `MODIFIED`에는 `modified_intent`가 필수다. 맥락 카탈로그 안이어야 하며 같은 gesture+context의 다른 기억과 중복될 수 없다. |
| M-4 | 승인 시 confidence를 `auto_execution_threshold` 이상으로 올리고, 같은 gesture+context의 다른 `ACTIVE` 기억은 모두 `CANDIDATE`로 강등한다. 자동 실행 기억은 조합당 최대 1개다. |
| M-5 | 거절 시 `REJECTED`, `auto_execute=false`, confidence −0.20. 같은 조합 재관찰 시 `CANDIDATE`로 복귀한다. |
| M-6 | `GET /memories`는 `ACTIVE`이며 confidence ≥ `auto_execution_threshold`인 기억만 반환한다. |

### 추론·실행 (FR-06, FR-10, FR-11)

| ID | 규칙 |
|---|---|
| I-1 | M-1의 후보 중 같은 사용자·`context_scope`만 추론한다. |
| I-2 | 점수 = `pattern.confidence × (0.75 × gesture_key 일치 + 0.25 × max(코사인 유사도, 0))`. 키가 다르면 최대 confidence의 25%다. |
| I-3 | 점수 < `auto_execution_threshold`(기본 0.60)면 실행하지 않고 사유를 반환한다. |
| I-4 | 모든 실행은 성공·실패와 무관하게 `executions`에 `SIMULATED`·`SUCCEEDED`·`FAILED`로 기록한다. |
| I-5 | 기본은 OS 제어 없이 결과만 표시하는 `DRY_RUN`. `SO_ENABLE_OS_ACTIONS=true`일 때만 실제 키를 보낸다. |
| I-6 | `SO_REQUIRE_ACTIVE_WINDOW=true`(기본)면 대상 앱 활성 여부를 확인한다. 비활성·확인 불가 시 키를 보내지 않고 `FAILED`와 사유를 UI에 표시한다. |
| I-7 | 미매핑 Intent는 키를 보내지 않고 `FAILED`로 기록한다. |

### 피드백 (FR-12, FR-13)

| ID | 규칙 |
|---|---|
| F-1 | 실행당 피드백은 1건이며 중복은 400이다. |
| F-2 | confidence 증감은 `CORRECT` +0.03, `WRONG_ACTION` −0.15, `ACCIDENTAL_GESTURE` −0.10, `IGNORE` −0.05이며 0~0.99로 제한한다. |
| F-3 | `WRONG_ACTION` + `corrected_intent`는 M-3 검증 후 기억의 Intent를 교정한다. |
| F-4 | confidence < `auto_execution_threshold`면 `auto_execute=false`, `CANDIDATE`로 강등한다. |

### 데모·UI (FR-15, FR-16)

| ID | 규칙 |
|---|---|
| D-1 | `POST /demo/reset`의 demo-user 삭제·재생성은 단일 트랜잭션이며 실패 시 이전 상태로 롤백한다. |
| D-2 | 종속 데이터는 `ON DELETE CASCADE`로 삭제하며 초기화 후 0건이고 재학습 가능해야 한다. |
| D-3 | `SO_DEMO_MODE=false`면 초기화는 403이며 데이터를 변경하지 않는다(기본 true). |
| U-1 | 카메라 영상을 노출하지 않고 Agent Orb·상태 텍스트로 인식을 전달한다. |
| U-2 | 명령 매핑 설정보다 AI가 배운 기억을 앞세우며 Gesture·Context·Intent·confidence를 표시한다. |
| U-3 | 실행 오버레이는 사용자를 막지 않으며 실패를 성공과 구분해 사유를 표시한다. |

UI는 Idle(공간 이해 대기), Listening(모션·Context 분석), Observation ready(후속 행동 선택), Learning progress(1/3→2/3→3/3), Suggestion pending(승인·거절), Execution overlay(Intent·confidence), Feedback(맞아요·아니에요)을 표현한다. 외부 입력의 상태 변화도 주기적으로 자동 갱신한다.

## 완료 기준

- P-1~P-4, M-1, I-6 충족; 맥락 분기 데모 시나리오 100% 통과; D-1~D-3 초기화·재학습 통과.
- 핵심 테스트와 SQL 계약 검증 전부 통과.
- 핵심 루프 데모 90초 이내, 발표 대본 3분 이내.

FR-16 Reset 응답은 기존 bootstrap 상태 필드에 deleted_counts를 추가한다. demo-user에 속한 contexts, gesture_observations, actions, gesture_patterns, agent_suggestions, executions, feedback의 삭제 건수를 반환하며 다른 사용자는 보존한다.
