# OS 실행 운영 가이드

기본 시연은 실제 키 입력 없이 결과만 표시하는 `DRY_RUN`입니다. 실제 앱을 제어할 때만 아래 절차를 적용합니다. 실행 규칙은 [SPEC I-4~I-7](../spec.md#추론실행-fr-06-fr-10-fr-11), 전체 설정과 기본값은 [config.py](../backend/src/silent_orchestra/config.py)가 소유합니다.

## 설치와 실행

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
