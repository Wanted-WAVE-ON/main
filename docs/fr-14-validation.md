# FR-14 영상·개인정보 보호

## 구현 현황 · 2026-09-09

API·DB 계약 검증 완료. 실제 카메라 네트워크 캡처 검증은 미실시다.

Observe 입력 모델은 extra=forbid로 정의되지 않은 필드를 거부한다. 정상 Observation은 frame_stored=false이며 DB의 ck_raw_frame_never_stored CHECK는 frame_stored=0만 허용한다. gesture_observations에는 이미지 BLOB·영상 경로 열이 없다.

웹캠은 메모리에서 Optical Flow 분석·로컬 미리보기를 수행한다. feature-only payload를 생성하며 duration_ms=430을 전송하고 embedding과 gesture_key는 서버에서 생성한다. 현재 클라이언트에 프레임 파일 저장·영상 업로드·얼굴 인식 경로는 없다.

Web UI는 Raw video storage OFF, Face recognition OFF, Cloud video upload OFF를 표시한다. GET /api/v1/demo/privacy의 고정 정책값과 이 UI 표시는 네트워크 측정 결과가 아니다.

## 경계의 의미

API는 motion_type·direction·duration_ms·numeric embedding 및 사용자·Context 메타데이터를 허용한다. 숫자 배열이라는 형식 검증만으로 임의 클라이언트가 넣은 embedding의 의미나 출처까지 판별하지는 않는다. 보호 보장은 현재 클라이언트 코드·허용 API 필드·저장 스키마의 범위로 해석한다.

## 수용 기준

- [x] AC-FR-14-01: 정상 Observation의 실제 DB frame_stored=0 및 허용 열 목록·BLOB 열 부재 검증.
- [x] AC-FR-14-02: 직접 SQL INSERT·UPDATE로 frame_stored=1을 시도하면 명명된 CHECK 제약으로 실패함을 검증.
- [x] AC-FR-14-03: OpenAPI의 ObserveRequest·ContextInput·GestureInput 허용 필드와 additionalProperties=false, embedding의 numeric array 계약 검증.
- [ ] AC-FR-14-04: 실제 카메라 실행 중 네트워크 요청 캡처로 raw frame 전송 0건 확인. 현재 로컬 워크스페이스는 카메라 프레임 읽기 실패(-2147467261)로 실제 촬영이 불가했고, 브라우저/서버 기반 Playwright 네트워크 캡처만으로는 프레임 raw payload를 증명할 수 없다.

추가 검증: frame, image, video, face, face_embedding, frame_stored를 요청 루트·context·gesture에 각각 주입한 18개 요청 모두 422이며 Dashboard 데이터가 변하지 않는다.

## 코드·테스트 근거

- backend/src/silent_orchestra/schemas.py
- backend/src/silent_orchestra/models.py
- backend/src/silent_orchestra/routers/demo.py
- backend/sql/schema.sql
- backend/scripts/webcam_gesture_client.py
- frontend/index.html
- backend/tests/test_api.py: 기존 privacy 테스트 및 test_privacy_openapi_observe_contract_is_closed, test_privacy_rejects_each_raw_field_without_writing_data, test_privacy_db_rejects_raw_frame_insert_and_update

검증: python -m pytest backend/tests -q — 40개 통과. SQLite schema·seed·queries·tests 검증 — 38문 통과.

네트워크 검증 시 실제 클라이언트의 Observe·Teach 요청을 확인하고, 카메라 실패·네트워크 오류 조건도 별도로 기록한다. 정책 API 응답을 캡처 검증의 대체 근거로 사용하지 않는다.
