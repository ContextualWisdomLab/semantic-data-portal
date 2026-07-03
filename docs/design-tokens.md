# Semantic Data Portal 디자인 토큰 / Figma 연계 기준

이 문서는 Figma에 정의된 KRDS 기반 디자인 시스템(파일 `JjYSqr6nWxpARUjaVKhG16`)을 실제 코드가 동일하게 소비하도록 만드는 토큰 계약을 정의한다. 운영자 콘솔(`GET /enterprise/console`)은 임의 hex/px 리터럴 대신 `src/sdp/design_tokens.py`가 정의한 CSS 변수를 참조한다.

## 핵심 판단

- 단일 원천: 모든 토큰은 `src/sdp/design_tokens.py`에 정의된다. `console.py`는 이 모듈의 `root_css_variables()`를 `:root`에 주입하고, 규칙에서는 `var(--sdp-*)`만 참조한다.
- 무회귀 리팩터: 토큰 값은 기존 콘솔에 실제로 배포되던 색/치수와 동일하다. 즉 토큰 도입은 렌더링 결과가 바뀌지 않는(byte-identical) 리팩터이며, `flatten()`과 `tests/test_design_tokens.py`가 이를 보장한다.
- Figma / 코드 역할 분리: Figma는 primitive·semantic tier를 Figma Variables로 소유한다. 코드는 component tier를 소유한다(렌더 표면이 직접 소비하기 때문). Figma Code Connect는 사용하지 않는다(`docs/enterprise-readiness.md` 참조).
- 이름 규칙: Figma 변수명과 CSS 변수명을 일치시킨다. 점을 대시로 바꾸고 `sdp` prefix를 붙인다. 예: Figma `color/text/primary` ↔ CSS `--sdp-color-text-primary`.

## 3계층 토큰 구조

| Tier | 정의 | 예시 | 소유 |
|---|---|---|---|
| Primitive | 문맥 없는 원시값 | `--sdp-color-gray-900: #17202a`, `--sdp-space-16: 16px` | Figma |
| Semantic | 의미 기반 alias | `--sdp-color-text-primary: var(--sdp-color-gray-900)` | Figma |
| Component | 컴포넌트 범위 alias | `--sdp-badge-success-fg: var(--sdp-color-status-success-fg)` | 코드 |

전체 토큰 목록은 `src/sdp/design_tokens.py`의 `PRIMITIVE` / `SEMANTIC` / `COMPONENT` OrderedDict를 원천으로 한다.

### 대표 semantic 매핑 (Figma ↔ CSS 변수 ↔ 최종값)

| Figma 변수 | CSS 변수 | 최종값 | 콘솔 사용처 |
|---|---|---|---|
| color/text/primary | `--sdp-color-text-primary` | `#17202a` | 본문 텍스트, 제목 |
| color/text/muted | `--sdp-color-text-muted` | `#5b6778` | eyebrow, label, code |
| color/surface/default | `--sdp-color-surface-default` | `#ffffff` | header, section, action |
| color/surface/muted | `--sdp-color-surface-muted` | `#f7f9fc` | badge, metric 배경 |
| color/background/canvas | `--sdp-color-background-canvas` | `#eef2f6` | body 배경 |
| color/border/default | `--sdp-color-border-default` | `#d8dee8` | 카드·표 경계선 |
| color/interaction/primary | `--sdp-color-interaction-primary` | `#0f766e` | hover/focus, progress bar |
| color/status/success/* | `--sdp-color-status-success-*` | `#166534` 외 | `.badge.ok` |
| color/status/warning/* | `--sdp-color-status-warning-*` | `#a16207` 외 | `.badge.warn` |
| radius/surface | `--sdp-radius-surface` | `8px` | section, metric, node |
| radius/control | `--sdp-radius-control` | `6px` | action, badge |

## Development Handoff — Figma ↔ 코드 컴포넌트 매핑

콘솔은 폼(button/input)이 없는 읽기 전용 증빙 표면이므로, 실제 존재하는 CSS 패턴만 Ready로 표기한다.

| Figma Component | Dev 선택자 / 위치 | Token | Status | Note |
|---|---|---|---|---|
| Chip / Badge | `.badge` / `.badge.ok` / `.badge.warn` (`console.py`) | `--sdp-badge-*` | Mapped | 상태를 색+텍스트로 전달(색만 아님) |
| Nav Link | `.action`(header), `.node`(flow) (`console.py`) | `--sdp-color-interaction-primary` | Mapped | `.node`에 `aria-label` 존재 |
| Card | `.metric`, `section` (`console.py`) | `--sdp-radius-surface` | Partial | 시각 패턴은 있으나 재사용 컴포넌트화 미완 |
| Table / List Item | `<table>`/`<tr>` (Controls/Connectors/KPI) | `--sdp-color-border-default` | Partial | 인라인 템플릿 렌더, 컴포넌트 아님 |
| Button | 없음(`<a class="action">`만 존재, `<button>` 아님) | `--sdp-color-interaction-primary` | Gap | 실제 `<button>` 도입 권장 |
| Input / Text Field | 없음(콘솔에 폼 없음) | `--sdp-color-border-default` | Gap | 폼 도입 시 error/focus 상태 필요 |
| Toast / Modal / Tooltip / Radio / Switch / Checkbox / Mobile Tab Bar / Logo | 없음 | — | Gap | Figma에는 존재, 코드 대응 표면 미존재 |

## Gap List

| Area | Issue | Severity | Required Action |
|---|---|---|---|
| Spacing | `--sdp-space-3/9/18` 등 4px 그리드 이탈 값 존재 | Medium | 4px 그리드로 정규화(배포 회귀 방지를 위해 현재는 실제 값 보존) |
| Component | 콘솔에 `<button>`/`<input>` 등 실제 인터랙션 컴포넌트 부재 | Medium | 폼/액션 도입 시 Figma Button/Input 상태(hover/focus/error) 반영 |
| Token modes | Dark / High-Contrast Variable Mode 미구현 | Low | Figma mode 도입 후 `data-theme` 기반 토큰 override 추가 |
| Figma 값 정합 | 초기 Figma primitive가 임의 blue였음 | — | 실제 제품 teal 팔레트로 재정합(이 문서 기준으로 통일) |

## 소비 방법

```python
from sdp.design_tokens import root_css_variables

# <style> 최상단에 :root 토큰 정의 블록을 주입
css = f"<style>{root_css_variables()} /* ... rules use var(--sdp-*) ... */</style>"
```

- `flatten()` : 모든 토큰을 최종 리터럴로 확장(alias 무결성 검증용).
- `resolve(value)` : 임의 `var(--sdp-*)` 문자열을 리터럴로 확장.

## 테스트

`tests/test_design_tokens.py`가 다음을 잠근다.

- 모든 토큰 alias가 리터럴로 해석된다(미정의 토큰 참조 시 실패).
- semantic/component tier는 리터럴이 아니라 다른 토큰만 alias 한다.
- 콘솔 규칙 영역에 raw hex가 남아 있지 않다(색은 전부 토큰 경유).
- 콘솔이 참조하는 모든 `var(--sdp-*)`가 정의되어 있고, `:root`가 모든 토큰을 선언한다.

## KRDS 스케일 확장 (v0.3)

`design_tokens.py`에 KRDS 스타일 스케일을 추가(전부 additive, 기존 토큰/값 불변, 콘솔 무회귀).

- **Primary ramp** `--sdp-color-primary-5..95`: KRDS `color.primary.5-95` 대응. 70 단계 == 제품 accent `#0f766e`에 앵커된 단조 teal ramp.
- **Space scale** `--sdp-space-0/32/40/48/64` 추가 → KRDS `space.0-64` 완성.
- **Radius** `--sdp-radius-0/2/4/12` primitive + `--sdp-radius-xs/sm/md/lg/xl/full` semantic alias(KRDS xsmall–xlarge, 2–12px).
- **추가 semantic**: `--sdp-color-brand-primary`, `--sdp-color-text-inverse`, `--sdp-color-text-disabled`, `--sdp-color-background-inverse`, `--sdp-color-border-strong`.

### High Contrast (선명한 화면 모드)

`HIGH_CONTRAST` 오버라이드 맵 + `high_contrast_css(selector='[data-theme="high-contrast"]')` 함수. semantic 토큰을 고대비 값으로 재정의하되 값은 전부 `var(--sdp-*)` 참조라 raw hex 없음. 기본 콘솔에는 주입하지 않음(opt-in). KRDS 대비 목표: 본문 7:1(기본)/15:1(HC), 헤딩·레이블 4.5:1/7:1, 아이콘·그래픽 3:1/4.5:1.
