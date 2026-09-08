# SilentOrchestra 2.0 프로젝트 브리프

기획 배경 문서입니다. 범위·지표·규칙은 [spec.md](../spec.md)가 소유합니다.

## 한 줄 정의

정해진 제스처를 인식하는 시스템이 아니라, 사용자의 행동 패턴과 상황을 관찰해 개인의 몸짓 언어를
스스로 학습하는 로컬 우선 Spatial AI Agent.

## 문제

기존 제스처 제어는 시스템이 미리 정한 동작을 사용자가 외우고 정확히 재현해야 합니다. 사용자의 자연스러운
습관을 반영하지 못하고, 같은 몸짓이 발표·음악처럼 상황에 따라 다른 의미를 가질 수 있다는 점을 다루지 못합니다.

## 대상 사용자

- 발표 중 키보드·리모컨에서 손을 떼고 화면을 제어하려는 사용자
- 음악 감상 중 같은 몸짓을 개인 습관대로 쓰고 싶은 사용자
- 고정된 제스처 명령 체계보다 학습되는 개인화 인터페이스가 필요한 사용자
- 카메라 기반 서비스에서 영상 저장과 얼굴 인식에 민감한 사용자

## 핵심 가치

1. **No gesture manual** — 정해진 제스처를 외우지 않음
2. **Context reasoning** — 같은 몸짓도 현재 활동에 따라 다른 의도로 해석
3. **Human approval first** — 반복 패턴을 발견해도 승인 전에는 자동 실행하지 않음
4. **Personal Gesture Memory** — AI가 사용자에 대해 배운 것을 가시화
5. **Privacy by design** — 원본 프레임은 폐기하고 모션 특징만 로컬 저장

## 차별점

```text
기존 Gesture Control
Gesture → Classifier → Command

SilentOrchestra 2.0
Observation → Context + History → Candidate Intent
→ Confidence → Suggestion/Execution → Feedback → Memory Update
```

## 기술 선택

FastAPI · SQLite + SQLAlchemy · Vanilla HTML/CSS/JS · 선택적 OpenCV Optical Flow ·
Pytest + FastAPI TestClient. 전부 local-first이며 원본 프레임은 폐기합니다.
선택 근거는 [decision-log.md](decision-log.md).

## 데모 메시지

> 사용자가 AI를 설정하는 것이 아니라, AI가 사용자의 자연스러운 몸짓 언어를 배운다.
