# TASKS — SilentOrchestra 2.0

## 진행 중

- [x] 2026-09-14: ERD·SQL 설계 문서(`docs/erd.md`, `backend/sql/schema.sql`)가 실제 `models.py`보다 뒤처져 있던 걸 재검증 후 반영. `gesture_observations.speed`·`amplitude`(FR-17 실측 입력, `CHECK (speed IS NULL) = (amplitude IS NULL)`)가 schema.sql·erd.md·seed.sql·queries.sql·tests.sql 어디에도 없었던 걸 schema.sql·erd.md에 추가(seed.sql은 컬럼 생략 시 NULL 기본값이라 수정 불필요). erd.md의 관계도에 `actions.user_id` 엣지, 누락됐던 인덱스 3개(`ix_contexts_user_activity`·`ix_observations_detected_at`·`ix_actions_user_type`)를 보완. `positive_feedback_count`/`negative_feedback_count`는 기록만 되고 어디서도 읽히지 않는 죽은 컬럼임을 확인했으나 그대로 두기로 함. `validate_sqlite.py` 재실행 38개 statement 통과, `pytest backend/tests` 114개 영향 없음.

- [ ] 2026-09-14: 웹 대시보드에서 사용자 동의 기반 카메라 미리보기와 로컬 좌우 손짓 감지를 추가한다. 원본 프레임을 전송·저장하지 않고 기존 Observation 계약으로만 연동하며, 브라우저 권한·중지·오류와 감지 회귀를 검증한다.
  - [x] 2026-09-14: `카메라 시작/중지`와 로컬 미리보기·좌우 모션 분석을 구현했다. 정지 화면 제외·합성 좌우 이동 감지 Node 회귀 테스트 4개를 통과했다.
  - [x] 2026-09-14: 가상 카메라 대신 실제 장치를 고르는 `입력 장치` 선택기, 손바닥 펼치기(배경 대비 정지 전경 지속)·원형 움직임(전경 중심점 누적 회전각) 감지를 추가했다. Node 회귀 테스트 3개(전경 비율·중심점, 손바닥 재무장, 원형 완전한 한 바퀴 대 1/4 회전 미검출)를 통과했다.
  - [ ] 2026-09-14: 브라우저 권한 허용 뒤 실제 `LGE Camera`를 선택기로 골라 네 가지 몸짓(swipe:right/left, open_palm:none, circle:clockwise) 모두에서 Observation 생성·중지 시 영상 트랙 해제를 수동 확인한다.
- [ ] 2026-09-14: Windows 카메라 미표시 원인을 장치·권한·OpenCV 캡처 경로로 나누어 진단하고, 실제 프레임 수신을 검증한다. 카메라 초기화 실패의 복구와 회귀 테스트를 보완한다.
  - [x] 2026-09-14: 첫 프레임 검증, Windows DirectShow→Media Foundation 전환, 실패 캡처 해제, `--check-camera` 진단과 회귀 테스트를 추가했다. 인덱스 2의 Mirametrix Virtual Camera는 DirectShow 640×480 프레임을 반환했다.
  - [ ] 2026-09-14: 재부팅 뒤 실제 `LGE Camera`의 `IsRebootRequired`는 해소됐지만 인덱스 0·1은 첫 프레임을 반환하지 않는다. LG Secure Mode·물리 프라이버시 셔터·다른 앱의 점유를 해제한 뒤 `--check-camera --camera 0` 및 swipe 수용 기준을 다시 확인한다.
- [ ] 2026-09-10: 현재 HEAD `edafa51` 기준 구조적 문제 수정: 앱 맥락 자동화, 실제 후속 조작 관측, 실측 embedding/유사도, 최근 학습·승자 강등·거절 억제·감지 오류 분리, 발표 Q&A 정합성 및 회귀 검증. 사용자 기준 `6b62db4`는 로컬에서 찾을 수 없음.
  - [x] 2026-09-10: 웹캠 클라이언트를 문서화된 계약에 맞췄다. `--input-mode observe|labels`, `--activity auto`, `--learn`, 실측 speed·amplitude 전송, 관측 모드의 5초·동일 맥락 첫 키 Teach 연결(`select_observed_teach`)을 구현하고 `input_observer`를 연결했다. `operations.md`의 존재하지 않는 플래그와 `fr-17-validation.md`의 옛 실행·수치를 갱신했다. pytest 78개 통과.
- [x] 2026-09-14: 구조 감사(A/B/C/D 목록) 재검증 후 잔여 3건 반영: (1) 파이썬 웹캠 클라이언트에 open_palm·circle 감지 추가(A-5) — 이미 계산 중이던 MOG2 전경 마스크로 손바닥 펼치기(정지 전경 지속)·원형 움직임(전경 중심점 누적 회전각)을 판별, `observation_payload`가 `motion_type`을 받도록 확장, pytest 7개 추가. (2) 원형 움직임에 반지름·회전속도를 speed·amplitude로 전송해 실측 개인차를 반영(A-3 잔여분, 브라우저·파이썬 양쪽). (3) 승자 선택 자체를 `_recency_weight` 가중합으로 변경(C-2 잔여분) — 이전엔 confidence에만 시간 가중이 곱해져 "누가 이기는지"는 raw count 그대로였음; `spec.md` L-3/L-5, `docs/decision-log.md` 갱신, 회귀 테스트로 라우 카운트 우세와 무관하게 최근 증거가 승자를 뒤집는 경우를 검증. `pytest backend/tests` 114개, `node --test frontend/tests/app.test.cjs` 7개 통과. A-1(라벨링 비용)·A-2(맥락 자동화)·A-4(유사도 가중)·C-1(강등)·C-3(거절 학습)·C-4(오작동 벌점)·D(winning_target)는 재확인 결과 이미 해결돼 있었다(각 `spec.md`·코드 근거는 대화 기록 참고). B-2(콜드스타트)·C-5(표현력 천장 전반)는 M-1 안전 원칙의 의도된 트레이드오프로 남겨둔다.
- [x] 2026-09-15: `codex/frontend-workbench`(워크벤치 미니멀 리디자인 + 튜토리얼/개인정보 연동/실행 감사 로그/OS 배지)를 `main`(카메라 손짓 인식, 맥락 자동 정규화, 실측 speed·amplitude, 최근성 가중 승자 선택)과 병합. `frontend/index.html`이 두 브랜치에서 독립적으로 재작성되어 충돌했던 걸, 카메라 손짓 인식 패널을 워크벤치 디자인 톤에 맞춰 다시 붙이는 방식으로 해결. `app.js`/`schemas.py`/`agent.py`/`styles.css`는 자동 병합됨. 병합된 app.js가 참조하는 DOM id(`cameraVideo`·`startCameraButton`·`stopCameraButton`·`cameraDeviceSelect`·`cameraPreview`·`cameraStatus`·`cameraLive`·`cameraMode`)를 전수 대조해 누락 없음을 확인. 입력 모드 배지가 브라우저 카메라 스트림도 우선 감지하도록 보완.
- [ ] FR-17 웹캠: 감지 로직 구현 후 하드웨어 검증 중. 선택 경로 시연 시 발표 환경의 조명·배경·프레임률에서 좌우 swipe 품질을 확인하고 [Notion](https://ken-jeong.notion.site/wave-on) 상태를 갱신한다.

## 할 일

- [ ] 발표자가 [대본](docs/demo-script.md)을 소리 내어 읽고 [시간 기준](spec.md#완료-기준)을 확인한다. 내레이션은 대본 331음절 기준 65~80초로 추정되며, UI 조작 약 15초를 더해도 3분 안에 든다. 실제 낭독 속도만 사람이 확인한다.
- [ ] OS 실행 시연 시에만 발표 PC에서 [운영 가이드](docs/operations.md)에 따라 설정·권한·대상 앱 매핑과 실행 결과를 확인한다.

## 검증 기록

- [x] 사용자 피드백에 따라 구체·동심원·그라데이션·영문 장식 문구를 제거하고, 상태 표시를 축소했다. 입력 영역을 위로 올리고 2열 버튼·얇은 구분선으로 정리했다. Node 회귀 테스트 3개 통과 및 로컬 좁은 화면 렌더링 확인.

- [x] Workbench 리디자인: 동심원 Agent 신호, 01·02 입력 단계, 맥락 레일·기억 목록과 한국어 지표를 적용했다. 기존 Node 회귀 테스트 3개 및 diff 검사 통과. 로컬 브라우저에서 데스크톱·390px 모바일 배치, 중복 ID 없음·가로 넘침 없음과 Presentation/Music 전환을 확인했다.

- [x] 2026-09-08: 아키텍처의 낮은 추론 점수 분기, 실행당 피드백 최대 1건 ERD, 행동 동률 Q&A를 규칙·구현에 맞췄다. OS 실행 절차를 `docs/operations.md`로 통합하고 README·PLAN·TASKS·Q&A·결정 로그에서 참조한다. ERD의 중복 검증 명령·결과와 오래된 PLAN 참조를 제거했다. 로컬 문서 링크·제목 앵커 66개 검증 통과. 문서만 변경하여 앱 테스트는 재실행하지 않았다.

- [x] 2026-09-08: main에서 Python 패키지·테스트·SQL·스크립트를 `backend/`, 정적 UI를 `frontend/`로 이동했다. 루트 `.env`·DB·데모 실행 진입점을 유지하고 CI·문서 링크를 갱신했다. pytest 23개, SQLite 38문, 프론트 4개 파일 응답·실행 진입점·설정 경로·로컬 문서 링크 검증 및 backend editable 설치 통과.

- [x] 2026-09-08: 로컬 변경을 stash에 보관하고 main을 `bb50fda`로 fast-forward한 뒤 staging 상태와 미추적 파일까지 복원했다. 원격 롤백 테스트의 제거된 `bootstrap` 호출을 로컬 자동 초기화 fixture에 맞춰 삭제했다. pytest 23개 및 SQLite 검증(38문) 통과. 복원 전 stash는 백업으로 유지한다.
- [x] 2026-09-09: waveon/main 최신 97d8e96을 반영하고 FR-17 변경을 backend 경로에 복원했다. 최소 모션 비율 0.01, 방향 판정·payload 분리, 카메라/API 오류 및 Simulation 안내를 보완했다. 전체 pytest 35개 통과. 실제 하드웨어 수용 기준은 [검증 기록](docs/fr-17-validation.md)에 미체크로 유지한다.
- [x] FR-15: Dashboard 오류·자동 복구, polling 중 제안 선택 보존, 외부 학습 진행률 코드 보완 및 자동 테스트 완료. 브라우저 검증은 별도 진행한다.
- [x] 2026-09-09: FR-15 Dashboard 오류·재시도, 중복 조회 방지, 제안 편집 보존, 외부 학습 진행률 및 실패 dialog 설명을 보완했다. Node 회귀 테스트 3개 통과. 브라우저 수용 기준은 [FR-15 검증 기록](docs/fr-15-validation.md)에 미체크로 남긴다.
- [x] FR-16: 삭제 건수 응답 및 Feedback 포함 전체 삭제·타 사용자 보존·3회 재학습·commit 실패 롤백 검증 완료. 전체 pytest 37개 통과. [검증 기록](docs/fr-16-validation.md), 브라우저 재시연은 미완료.
- [x] FR-14: 원본 필드 18개 비정상 요청·OpenAPI 허용 계약·DB INSERT/UPDATE CHECK 검증 추가. 전체 pytest 40개 및 SQLite 38문 통과. [검증 기록](docs/fr-14-validation.md)의 실제 카메라 네트워크 캡처 항목은 미완료.
