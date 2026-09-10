# 웹캠 관측과 OS 실행 운영 가이드

기본 시연은 버튼·라벨 시뮬레이션과 `DRY_RUN`입니다. 웹캠의 실제 후속 조작 관측과 Agent의 OS 키 전송은 별도 기능입니다. 관측만 사용하면 사용자가 누른 키로 앱이 움직이고, Agent가 키를 보내려면 OS 실행을 따로 활성화해야 합니다. 규칙은 [SPEC](../spec.md), 서버 설정은 [config.py](../backend/src/silent_orchestra/config.py), CLI 인자는 [웹캠 클라이언트](../backend/scripts/webcam_gesture_client.py)가 소유합니다.

## 웹캠 학습과 실제 조작 관측

[README 시작하기](../README.md#시작하기)에 따라 서버를 실행합니다. 별도 터미널에서 가상환경을 활성화한 뒤 저장소 루트에서 실행합니다.

```bash
python -m pip install -e "./backend[camera]"
python backend/scripts/webcam_gesture_client.py --learn
```

기본값은 `--input-mode observe --activity auto`이며 실제 키 관측은 Windows에서 지원합니다. `--learn`은 승인된 기억이 있어도 추론을 끄므로 초기 학습과 습관 변경에 사용합니다. 관측 모드는 실제 활성 창을 읽으며 `--active-app`으로 앱을 가장하지 않습니다.

발표 리허설에서 PowerPoint 슬라이드 쇼 또는 지원 음악 앱을 활성화하고 좌우 손짓 뒤에 평소 쓰던 키를 누릅니다. 앱·맥락이 같은 상태에서 관찰 후 5초 안에 발생한 첫 허용 조작만 학습에 연결합니다. 합성 입력, 수정 키 조합, 길게 눌러 반복된 키, 자동 실행된 관찰과 만료된 관찰은 학습에서 제외합니다. 관측기는 원래 키 전달을 막지 않습니다.

| 활성 앱 | 실제 관측하는 키 | 행동 |
|---|---|---|
| PowerPoint 슬라이드 쇼 | Right / PageDown / N / Space | 다음 슬라이드 |
| PowerPoint 슬라이드 쇼 | Left / PageUp / P | 이전 슬라이드 |
| PowerPoint 슬라이드 쇼 | Escape | 발표 종료 |
| Spotify / VLC / iTunes / Music | 하드웨어 Media Next / Previous / PlayPause | 다음 트랙 / 이전 트랙 / 재생·일시정지 |

PowerPoint 편집 화면·다른 발표 앱은 실제 키 관측 대상이 아닙니다. PowerPoint의 B는 화면 가리기이므로 이전 슬라이드로 해석하지 않습니다. 음악 앱의 일반 Space는 검색창 입력과 구분할 수 없어 관측하지 않습니다. 앱 판정은 창 정보에 의존하므로 실제 발표 장비에서 확인해야 합니다.

활동을 판정하지 못하거나 두 활동으로 모호하게 매칭되면 관찰을 생성하지 않습니다. API에서도 activity가 없으면 active_app, 그마저 없으면 서버의 활성 창으로 판정합니다. space·device는 활동 판정에 사용하지 않습니다. 명시적 activity는 수동 override입니다.

웹 UI에서 제안을 검토·승인한 다음 클라이언트를 종료하고 `--learn` 없이 다시 실행합니다. 카메라 창의 Q 또는 터미널의 Ctrl+C로 종료할 수 있습니다. 승인·피드백은 수동이며 리허설까지 hands-free는 아닙니다. 실측 특징의 차원이 달라 기존 버튼 시뮬레이션 기억은 웹캠에 적용되지 않으므로 이 경로에서 다시 학습합니다.

### 라벨 시뮬레이션과 감지 조정

Windows 실제 입력 관측을 사용할 수 없는 환경에서는 다음과 같이 명시적으로 라벨 모드를 실행합니다.

```bash
python backend/scripts/webcam_gesture_client.py --input-mode labels --activity presentation --learn
```

카메라 창에 포커스를 두고 N/B로 다음·이전 행동을 라벨링합니다. `--activity music`에서는 Space도 재생·일시정지 라벨입니다. 이 입력은 `/teach`만 호출하며 실제 앱 조작을 관측하거나 대신 수행하지 않습니다. `--active-app`은 라벨 모드의 메타데이터 override입니다.

감지는 좌우 반전된 미리보기의 좌우 swipe만 지원합니다. 움직이는 전경의 방향 안정성과 움직임 종료 구간으로 지속 시간·ROI 너비 기준 속도·진폭을 계산합니다. 조명·배경에 따라 `--threshold`, `--min-motion-ratio`, `--stable-frames`를 조정할 수 있습니다. 재감지 간격 1.2초와 관측 연결 창 5초는 클라이언트 상수입니다. 현재 값과 실기 확인 항목은 [FR-17 검증 기록](fr-17-validation.md)을 참고합니다.

카메라·키 훅·API 오류 시 출력된 사유를 확인하고 버튼 기반 Stable Simulation으로 전환합니다. API 요청은 자동 재전송하지 않습니다. 프레임은 메모리에서만 처리하며 저장·전송하지 않습니다.

## OS 실행 설치와 실행

[README 시작하기](../README.md#시작하기)에 따라 설치한 뒤, 저장소 루트에서 가상환경을 활성화합니다. 기존 서버가 실행 중이면 종료하고 같은 셸에서 실행합니다.

```bash
python -m pip install pyautogui
export SO_ENABLE_OS_ACTIONS=true
python run_demo.py
```

Windows PowerShell에서는 `export` 대신 `$env:SO_ENABLE_OS_ACTIONS = "true"`를 사용합니다. 설정은 서버 시작 시 읽으므로 변경 후 서버를 다시 실행합니다.

## 권한과 활성 창 확인

`SO_REQUIRE_ACTIVE_WINDOW=true`가 기본입니다. 키 입력 시점에 대상 앱을 활성 창으로 둡니다. 앱·창 이름은 대소문자를 구분하지 않는 부분 문자열로 확인하며, 매핑 원본은 [action_executor.py의 TARGET_WINDOWS](../backend/src/silent_orchestra/services/action_executor.py)입니다. 발표 앱이 목록에 없을 때만 해당 이름을 추가합니다.

- macOS: 접근성 권한을 허용하면 프로세스 이름과 창 제목으로 판정합니다. 창 제목을 읽을 권한이 없으면 프로세스 이름만 사용하므로 브라우저의 `Google Slides`를 구분하지 못할 수 있습니다. 프로세스 이름도 확인할 수 없으면 실행을 차단합니다.
- Windows: 현재 활성 창의 제목으로 판정합니다.
- Linux(X11/Wayland): 현재 구현은 활성 창 확인을 지원하지 않습니다. 기본 DRY_RUN으로 시연합니다. Linux에서 실제 키 입력이 꼭 필요할 때만 `SO_REQUIRE_ACTIVE_WINDOW=false`를 최후 수단으로 고려합니다. 이 설정은 대상 앱 확인을 생략합니다.

## 실행 확인과 실패 대응

승인된 기억을 같은 맥락에서 다시 관찰한 뒤 실행 결과를 확인합니다. 시연 흐름은 [데모 대본](demo-script.md)을 따릅니다.

| 결과 | 확인 및 대응 |
|---|---|
| `SIMULATED` | DRY_RUN 결과입니다. 실제 제어가 목적이면 OS 실행 설정과 서버 재시작 여부를 확인합니다. |
| `SUCCEEDED` | 키 전송이 완료되었습니다. 대상 앱의 실제 반응도 확인합니다. |
| `FAILED`: 대상 앱 비활성 | 대상 창을 활성화하고 앱 이름 매핑을 확인합니다. |
| `FAILED`: 활성 창 확인 불가 | OS 지원 여부와 권한을 확인합니다. |
| `FAILED`: 키 매핑 없음·키 전송 오류 | 표시된 사유와 `action_executor.py`의 `KEY_MAP`, PyAutoGUI 설치 상태를 확인합니다. |

현장에서 해결되지 않으면 서버를 종료하고 `SO_ENABLE_OS_ACTIONS=false`로 설정해 다시 실행한 뒤 DRY_RUN으로 시연합니다. PowerShell에서는 `$env:SO_ENABLE_OS_ACTIONS = "false"`를 사용합니다. 실제 발표 PC의 확인 상태는 [TASKS](../tasks.md)에 기록합니다.
