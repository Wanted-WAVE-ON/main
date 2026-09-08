# TASKS — SilentOrchestra 2.0

## 진행 중

- [ ] FR-17 웹캠: 감지 로직 구현 후 하드웨어 검증 중. 선택 경로 시연 시 발표 환경의 조명·배경·프레임률에서 좌우 swipe 품질을 확인하고 [Notion](https://ken-jeong.notion.site/wave-on) 상태를 갱신한다.

## 할 일

- [ ] 발표자가 [대본](docs/demo-script.md)을 소리 내어 읽고 [시간 기준](spec.md#완료-기준)을 확인한다. 내레이션은 대본 331음절 기준 65~80초로 추정되며, UI 조작 약 15초를 더해도 3분 안에 든다. 실제 낭독 속도만 사람이 확인한다.
- [ ] OS 실행 시연 시에만 발표 PC에서 [운영 가이드](docs/operations.md)에 따라 설정·권한·대상 앱 매핑과 실행 결과를 확인한다.

## 검증 기록

- [x] 2026-09-08: 아키텍처의 낮은 추론 점수 분기, 실행당 피드백 최대 1건 ERD, 행동 동률 Q&A를 규칙·구현에 맞췄다. OS 실행 절차를 `docs/operations.md`로 통합하고 README·PLAN·TASKS·Q&A·결정 로그에서 참조한다. ERD의 중복 검증 명령·결과와 오래된 PLAN 참조를 제거했다. 로컬 문서 링크·제목 앵커 66개 검증 통과. 문서만 변경하여 앱 테스트는 재실행하지 않았다.

- [x] 2026-09-08: main에서 Python 패키지·테스트·SQL·스크립트를 `backend/`, 정적 UI를 `frontend/`로 이동했다. 루트 `.env`·DB·데모 실행 진입점을 유지하고 CI·문서 링크를 갱신했다. pytest 23개, SQLite 38문, 프론트 4개 파일 응답·실행 진입점·설정 경로·로컬 문서 링크 검증 및 backend editable 설치 통과.

- [x] 2026-09-08: 로컬 변경을 stash에 보관하고 main을 `bb50fda`로 fast-forward한 뒤 staging 상태와 미추적 파일까지 복원했다. 원격 롤백 테스트의 제거된 `bootstrap` 호출을 로컬 자동 초기화 fixture에 맞춰 삭제했다. pytest 23개 및 SQLite 검증(38문) 통과. 복원 전 stash는 백업으로 유지한다.
