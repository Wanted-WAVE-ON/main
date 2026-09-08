# Design — SilentOrchestra 2.0

이 앱의 고정된 디자인 시스템입니다. 페이지를 다시 그릴 때마다 먼저 읽고, 페이지별 임의 테마는 만들지 않습니다.
시스템을 넓혀야 하면 이 파일을 고칩니다.

**토큰 값의 출처는 [`frontend/tokens.css`](../frontend/tokens.css)** 입니다(색·타입·간격·모션·radius·shadow·z-index 전체).
DTCG 형식은 [`design/design-tokens.json`](../design/design-tokens.json). 이 문서는 값이 아니라
**값만 봐서는 알 수 없는 규칙**을 담습니다.

## Genre

Atmospheric, with a technical Workbench voice. 캔버스는 어둡지만 페이지를 끌고 가는 것은 분위기가 아니라 기능입니다.

## Macrostructure — Workbench

주 작업 레일이 먼저 오고, 맥락과 학습된 근거가 데스크톱에서는 옆에, 모바일에서는 뒤에 붙습니다.

`primary=agent-flow`, `context=left-rail`, `evidence=right-rail`, `mobile=center-first`, `containment=single-layer`

마케팅·콘텐츠 페이지는 현재 없습니다.

## Theme — Night Signal

- accent(cyan) 사용 면적은 뷰포트의 5% 미만으로 유지합니다.
- `--color-learning`(violet)은 장식이 아닙니다. **suggestion·learning 상태만** 식별합니다.
- 상태는 색만으로 전달하지 않고 항상 텍스트·아이콘을 병행합니다(WCAG AA).

## Typography

- Display: IBM Plex Sans KR 700, tracking -0.035em
- Body: Pretendard Variable 400–600
- Outlier: IBM Plex Mono 500 — **wordmark와 live metric에만**

`swap`으로 로드하며 한국어 시스템 폴백을 유지합니다.

## Motion

- 프리미티브는 버튼 press와 상태 crossfade **둘뿐**입니다.
- ambient loop와 page-load reveal은 없습니다.
- reduced motion: opacity만, 최대 120ms.

## Microinteractions

- 결과 상태가 이미 화면에 보이면 성공은 조용히 처리합니다(토스트 없음).
- 고정 토스트는 오류나 화면 밖 비동기 결과에만 씁니다.
- 모든 컨트롤에 default·hover·focus·active·disabled·loading·error·success가 있습니다.
- focus ring은 즉시 나타나고, 터치 타깃은 최소 44px입니다.

## CTA

- Primary: solid cyan, 어두운 텍스트, radius 10px, 구체적인 한국어 동사
- Secondary: 어두운 raised 표면 + rule 보더, primary와 같은 높이·radius
- Destructive: secondary 표면에 error 색 **텍스트**. 빨강으로 채운 버튼은 쓰지 않습니다.

## 페이지 간 공유 / 차이

| 항상 공유 | 달라도 되는 것 |
|---|---|
| SilentOrchestra 워드마크 | 밀도와 evidence 패널 개수 |
| Night Signal 팔레트와 의미 역할 | 넓은 화면에서 sticky로 둘 레일 |
| IBM Plex Sans KR + Pretendard 조합 | learning violet의 등장 여부 |
| Workbench 버튼·필드 보이스 | |
| 모바일 우선 주 작업 순서 | |

앱 페이지는 enrichment를 쓰지 않습니다. 제품 상태 자체가 시각적 내용입니다.
