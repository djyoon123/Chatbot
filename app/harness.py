"""
harness.py — FAQ 챗봇 3-에이전트 하네스 (STEP 5)

파이프라인:
  1) 검색 에이전트  : 질문 → 관련 규정 조항 top-k 검색 (retriever, 오프라인)
  2) 답변 에이전트  : 검색 조항(근거)만 사용해 답변 생성
  3) 검증 에이전트  : 답변의 각 주장이 근거 조항과 매칭되는지 조항 단위로 검증

사람은 검증 리포트를 보고 최종 신뢰 여부만 판단 (HITL).
"""

from __future__ import annotations

from pathlib import Path
from retriever import Retriever, Chunk

APP_DIR = Path(__file__).resolve().parent
MODEL = "gpt-4o"

# ---------------------------------------------------------------------------
# 시스템 프롬프트
# ---------------------------------------------------------------------------

ANSWER_SYSTEM = """\
당신은 회사의 '인사관리 FAQ 어시스턴트'입니다. 사내 인사규정(근태·공수·복지 등)과 상위 법령인 근로기준법을 근거로 답합니다.

[답변 규칙 — CoT 자기점검 절차를 반드시 따르세요]

▶ 작성 절차 (순서 엄수):
1. 질문을 세부 항목으로 분해하고, 각 항목에 대응하는 <근거> 조항을 매핑하라 (누락 점검).
2. 각 주장을 쓰기 전, 그 근거가 <근거> 안에 실제로 있는지 1:1 대조하라.
3. 근거가 없는 내용은 절대 생성하지 말고, 있더라도 불확실하면 '(확인 필요)'를 붙여라.
4. 점검을 마친 뒤 최종 답변을 출력하라.

▶ 법령 우선 원칙:
- 근로기준법은 최저기준이다(근로기준법 제3조). 사내규정이 근로기준법보다 근로자에게
  불리하면 근로기준법이 우선함을 명시하라.
- 사내규정과 근로기준법이 모두 근거에 있으면 둘 다 인용하고 관계를 설명하라.

▶ 출력 형식:
- 결론 먼저, 그다음 근거 조문 제시
- 답변 끝에 반드시 `(출처: 문서 › 조문)` 형식으로 출처 표기
- 금액·비율 등 수치는 정확히 인용 (임의 변경 금지)
- 근거에서 답 못 찾으면: "제공된 규정에서는 확인되지 않습니다. 관련 담당 부서에 문의하세요."
"""

CHECKER_SYSTEM = """\
당신은 규정 인용 정확성을 검증하는 '검증 에이전트'입니다.

아래 <답변>의 각 주장이 <근거 조항>에 실제로 존재하는지 조항 매칭표로 검증하세요.

출력 형식 (표):
| 주장 요약 | 근거 조항 | 매칭 결과 |
|-----------|-----------|-----------|
| ...       | ...       | ✅ 근거 있음 / ⚠️ 부분 일치 / ❌ 근거 없음 |

마지막 줄에 종합 평가 한 줄:
- 모두 근거 있음 → "✅ 모든 주장이 규정에 근거합니다."
- 일부 미확인 → "⚠️ 일부 주장([확인 필요] 항목)은 담당 부서 확인이 필요합니다."
- 근거 없음 포함 → "❌ 규정 밖 내용이 포함됐습니다. 답변을 재검토하세요."
"""


# ---------------------------------------------------------------------------
# 에이전트 함수
# ---------------------------------------------------------------------------

def _call_llm(client, system: str, user: str) -> str:
    """단발 LLM 호출 (OpenAI Chat Completions, non-streaming). 결과 텍스트 반환."""
    resp = client.chat.completions.create(
        model=MODEL,
        max_tokens=2000,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content


def answer_agent(client, question: str, context: str) -> str:
    """근거 조항만 사용해 답변 생성."""
    user_content = (
        f"<근거>\n{context}\n</근거>\n\n"
        f"위 근거만을 바탕으로 다음 질문에 답하세요.\n질문: {question}"
    )
    return _call_llm(client, ANSWER_SYSTEM, user_content)


def checker_agent(client, draft: str, context: str) -> str:
    """답변의 각 주장이 근거 조항과 매칭되는지 검증."""
    user_content = (
        f"<근거 조항>\n{context}\n</근거 조항>\n\n"
        f"<답변>\n{draft}\n</답변>\n\n"
        f"위 답변의 각 주장이 근거 조항에 실제로 있는지 조항 매칭표로 검증하세요."
    )
    return _call_llm(client, CHECKER_SYSTEM, user_content)


def build_context(results: list[tuple[Chunk, float]]) -> str:
    blocks = []
    for i, (chunk, _score) in enumerate(results, 1):
        blocks.append(f"[근거 {i}] 출처: {chunk.source}\n{chunk.text}")
    return "\n\n".join(blocks)


# ---------------------------------------------------------------------------
# 하네스 (3-에이전트 파이프라인)
# ---------------------------------------------------------------------------

def harness(client, retriever: Retriever, question: str, k: int = 4) -> tuple[str, str, list]:
    """
    Returns:
        draft   — 답변 에이전트 출력
        report  — 검증 에이전트 출력
        results — 검색 결과 [(Chunk, score), ...]
    """
    # 1) 검색 에이전트
    results = retriever.search(question, k=k)
    if not results:
        no_ctx = "(관련 규정을 찾지 못했습니다.)"
        draft = answer_agent(client, question, no_ctx)
        return draft, "검색된 근거 조항이 없어 검증을 생략합니다.", results

    context = build_context(results)

    # 2) 답변 에이전트
    draft = answer_agent(client, question, context)

    # 3) 검증 에이전트
    report = checker_agent(client, draft, context)

    return draft, report, results
