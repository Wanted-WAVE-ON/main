# FR-17 웹캠 몸짓 감지 검증

상태: 검증 중. 실제 카메라 및 발표 환경 수용 기준은 미체크로 유지한다.

## 실행

저장소 루트에서 실행한다.

```sh
python -m pip install -e "./backend[camera,dev]"
python run_demo.py
# 별도 터미널 (Windows 실기 관측)
python backend/scripts/webcam_gesture_client.py --learn
# 다른 플랫폼 또는 키 훅을 쓸 수 없을 때
python backend/scripts/webcam_gesture_client.py --input-mode labels --activity presentation --learn
```

기본 threshold=1.0, min-motion-ratio=0.01, stable-frames=3, 재감지 간격은 monotonic clock 기준 1.2초다.
좌우 반전된 미리보기의 방향을 사용하며 ROI의 움직이는 전경 픽셀만 집계한다.
duration_ms는 움직임 구간의 실측값이고 speed·amplitude는 ROI 너비 기준 실측 특징이다. motion_type, direction, 이 특징과 context를 전송하고 gesture_key와 embedding은 서버가 생성한다.
프레임은 메모리에서만 처리하고 저장·전송하지 않는다.

관측 모드(기본, Windows)는 서버가 활성 창으로 맥락을 판정하고, 몸짓 관찰 후 5초 안에 같은 앱·맥락에서 실제로 누른 첫 탐색·미디어 키만 Teach로 연결한다. 합성 키·수정 키 조합·길게 눌러 반복된 키·자동 실행된 관찰·만료된 관찰은 제외한다.
라벨 모드(`--input-mode labels`)는 N/B로 Context별 다음·이전, `--activity music`에서는 Space로 재생/일시정지를 사람이 라벨링하며 `/teach`만 호출한다.
Q로 종료한 뒤 출력된 서버 URL에서 버튼 기반 Stable Simulation을 사용할 수 있다.
카메라 열기·읽기·처리 또는 API 실패 시 오류를 출력하고 카메라를 해제한다.
API 오류는 자동 재전송하지 않는다. 서버 연결 복구 후 Simulation을 사용하거나 클라이언트를 재실행한다.
웹 UI는 기존 startAutoRefresh에서 외부 입력 상태를 3초마다 갱신한다.

## 자동 검증

`python -m pytest backend/tests -q`: 78 passed (카메라 의존성 설치 환경).
NumPy가 없는 환경에서는 해당 의존성이 필요한 테스트를 건너뛴다.
합성 flow의 좌우 방향과 amplitude, 작은 모션·수직·정지·배경 제외, ROI 기준 속도·진폭의 정규화·클램프,
측정 payload의 Observation API 처리와 서버 11차원 embedding 생성,
관측 모드 Teach 연결 규칙(같은 맥락의 첫 키, 창 만료), 상충 플래그 거부,
카메라 열기·읽기 실패 및 네트워크 오류 시 자원 해제를 검증한다.
실기 키 훅과 실제 카메라 인식률은 보장하지 않는다.

## 현장 수용 기준

- [ ] AC-FR-17-01: 발표 장비에서 오른쪽 모션으로 swipe:right Observation 생성 확인. 로컬 워크스페이스는 실제 카메라 장치 0의 frame read 실패(-2147467261)로 이 항목은 미체크 상태다.
- [ ] AC-FR-17-02: 실제 클라이언트 요청을 검사해 이미지·프레임 데이터 부재 확인. 카메라 자체가 열리지 않아 클라이언트 request가 생성되지 않았다.
- [ ] AC-FR-17-03: 실제 카메라 권한 거부·장치 부재에서 오류와 Simulation 전환 확인. 실제 장치 인덱스 0에서 메모리/동영상 캡처는 실패했고 Simulation 문구만 출력됐다.
- [ ] 조명·배경·카메라·프레임률별 좌우 시도 횟수, 성공·오탐·미탐 기록.
- [ ] 웹캠 Observe → Teach → 웹 UI 제안 자동 갱신 → 승인 → 재인식 E2E-05 확인.
