# 제출 원고

이 디렉터리는 패키징 전, 제출용 Markdown 원고를 보관합니다.

권장 흐름:

1. `proposal.md`에 실제 원고를 작성합니다.
2. Run `python3 scripts/review_submission_source.py docs/submissions/proposal.md`.
3. `python3 scripts/render_markdown_submission.py`로 렌더링합니다.
4. 최종 첨부본 점검 단계에서만 `python3 scripts/review_submission_pdf.py output/pdf/proposal.pdf`를 실행합니다.
