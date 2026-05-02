# Ralph 기반 시각화 작업 흐름

## 1. 목적

이 저장소는 SummitHarness의 Ralph loop를 이용해 모델 견본과 제출용 시각화 자료를 함께 관리합니다.

핵심은 PDF를 바로 꾸미는 것이 아니라, 아래 source를 먼저 만든 뒤 render/review 단계로 넘기는 것입니다.

```text
CSV / Python script / Markdown source / SVG figure
-> source review
-> render
-> PDF review
```

## 2. 이번 프로젝트의 Ralph 설정

| 항목 | 값 |
|---|---|
| workflow profile | proposal-only |
| mode | proposal |
| reference pack | editorial-signal |
| 보조 성격 | analyst-workbench |
| 목표 | AI 모델 견본과 제출용 시각화 자료 생성 |

## 3. 시각화 산출물

| 파일 | 역할 |
|---|---|
| `reports/figures/01_ai_pipeline.svg` | 생활권 생성 AI, 평소패턴 학습 AI, 점수화, 케어 판단 흐름 |
| `reports/figures/02_score_structure.svg` | 최종 점수 4종 구조 |
| `reports/figures/03_decision_flow.svg` | 추가 리워드, 기본 유지, 예방 케어 판단 흐름 |
| `reports/model_demo_summary.md` | 모델 결과 요약 리포트 |
| `docs/submissions/proposal.md` | 제출용 제안서 source |

## 4. 실행 명령

환경 점검:

```bash
python3 scripts/preflight.py run
```

컨텍스트 갱신:

```bash
python3 scripts/context_engine.py refresh --source setup
```

제안서 source 검토:

```bash
python3 scripts/review_submission_source.py docs/submissions/proposal.md
```

제안서 render:

```bash
python3 scripts/render_markdown_submission.py
```

PDF 검토:

```bash
python3 scripts/review_submission_pdf.py output/pdf/proposal.pdf
```

Ralph loop:

```bash
./ralph.sh
```

## 5. 시각화 원칙

- 검정 중심, 회색 보조, 장식색 최소화.
- 그림은 “예쁘게 보이는 자료”가 아니라 “심사위원이 구조를 이해하는 증거”여야 한다.
- 생활권 밖 주행을 무조건 위험으로 표현하지 않는다.
- 위험행동 증가와 평소패턴 변화가 함께 나타날 때 예방 케어로 연결한다.
- 고객용 안내와 보험사 직원용 리포트는 분리한다.

## 6. 향후 커밋 흐름

```text
feat : 시각화 자료 생성 스크립트 추가
report : 기본 시각화 자료 생성
report : 모델 결과 요약 리포트 추가
docs : 제출용 제안서 source 작성
```
