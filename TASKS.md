# TASKS — SilentOrchestra 2.0

[SPEC.md](SPEC.md) · [PLAN.md](PLAN.md)

## 진행 중

- [ ] FR-17 웹캠: 감지 로직 구현 후 하드웨어 검증 중. 선택 경로 시연 시 발표 환경의 조명·배경·프레임률에서 좌우 swipe 품질을 확인하고 [Notion](https://ken-jeong.notion.site/wave-on) 상태를 갱신한다.

## 할 일

- [ ] 발표자가 [대본](docs/demo-script.md)을 소리 내어 읽고 [시간 기준](SPEC.md#완료-기준)을 확인한다. 내레이션은 대본 331음절 기준 65~80초로 추정되며, UI 조작 약 15초를 더해도 3분 안에 든다. 실제 낭독 속도만 사람이 확인한다.
- [ ] OS 실행 시연 시에만 발표 PC에 `pyautogui` 설치, `SO_ENABLE_OS_ACTIONS=true`, 접근성 권한을 확인한다.
- [ ] OS 실행 시연 시에만 [TARGET_WINDOWS](src/silent_orchestra/services/action_executor.py)에 실제 앱 이름을 추가한다.

## 완료

- [x] FR-01~FR-16 구현. 2026-09-07 측정: Pytest 21 passed, SQLite 38 statements passed; CI에 두 검증 연결.
- [x] 초기화 후 UI 리허설 7개 비트 통과. 피드백 접근을 위해 오버레이 자동 닫힘 제거(Esc·바깥 클릭·피드백으로 닫힘), `/static/*`에 `no-cache`와 ETag 304 적용.
- [x] Notion 기획서·기능 정의서 테스트 수치를 5→21 passed로 갱신.
- [x] 2026-09-07 브라우저 리허설 재실행: 초기화 → 학습 3회 → 제안 승인 → 자동 실행 → 피드백 → Music 맥락 분기까지 7개 비트 통과. 같은 `swipe:right`가 presentation/NEXT_SLIDE(0.90)·music/NEXT_TRACK(0.87) 두 기억으로 공존하며, 승인 전 자동 실행 0회(M-1)와 피드백 +0.03(F-2)을 확인했다.
