"""
chatbot.py — 인사관리 FAQ 챗봇 (RAG + 3-에이전트 하네스, OpenAI gpt-4o 기반)

파이프라인 (STEP 5 하네스):
  질문 → 검색 에이전트(retriever) → 답변 에이전트(OpenAI) → 검증 에이전트(OpenAI)
  사람은 검증 리포트를 보고 최종 신뢰 여부만 판단 (HITL).

사용법:
  설정:   $env:OPENAI_API_KEY="sk-..."
  대화:   python chatbot.py
  단발:   python chatbot.py "연차휴가 며칠 발생해?"
  오프라인(키 없이 검색만):  python chatbot.py --offline "연차휴가 며칠 발생해?"
  하네스 없이(단순 모드):     python chatbot.py --simple "질문"
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from retriever import Retriever, Chunk, text_similarity
from harness import harness, build_context

MODEL = "gpt-4o"
APP_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# 단순 모드 시스템 프롬프트 (--simple 플래그용, CoT 자기점검 포함)
# ---------------------------------------------------------------------------

SIMPLE_SYSTEM = """\
당신은 회사의 '인사관리 FAQ 어시스턴트'입니다. 사내 인사규정(근태·공수·복지 등)과 상위 법령인 근로기준법을 근거로 답합니다.

[답변 절차 — 반드시 순서대로]
1. 질문을 세부 항목으로 분해하고, 각 항목에 대응하는 <근거> 조항을 매핑하라 (누락 점검).
2. 각 주장을 쓰기 전, 그 근거가 <근거> 안에 실제로 있는지 1:1 대조하라.
3. 근거가 없는 내용은 쓰지 말고, 불확실하면 '(확인 필요)'를 붙여라.
4. 점검을 마친 뒤 최종 답변을 출력하라.

[법령 우선 원칙]
- 근로기준법은 최저기준이다(근로기준법 제3조). 사내규정이 근로기준법보다 근로자에게
  불리하면 근로기준법이 우선함을 명시하라.
- 사내규정과 근로기준법이 모두 근거에 있으면 둘 다 인용하고 관계를 설명하라.

[출력 규칙]
- 결론 먼저, 그다음 근거 조문 제시
- 답변 끝에 반드시 `(출처: 문서 › 조문)` 형식으로 출처 표기
- 금액·비율 등 수치는 정확히 인용 (임의 변경 금지)
- 근거에서 답 못 찾으면: "제공된 규정에서는 확인되지 않습니다. 관련 담당 부서에 문의하세요."
- 간결하고 명확한 한국어로 답하세요.
"""


def load_faq() -> dict:
    return json.loads((APP_DIR / "faq.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 오프라인 모드
# ---------------------------------------------------------------------------

def best_faq(question: str, faq: dict) -> tuple[dict | None, float]:
    """질문과 가장 유사한 FAQ 항목과 유사도를 반환."""
    best, best_score = None, 0.0
    for item in faq.get("items", []):
        s = text_similarity(question, item["question"])
        if s > best_score:
            best, best_score = item, s
    return best, best_score


def answer_offline(retriever: Retriever, question: str, faq: dict) -> None:
    """API 키 없이 동작하는 답변기.
    1순위: FAQ(검증된 사전 답변) 매칭, 2순위: 검색 조문 발췌 안내."""
    item, fscore = best_faq(question, faq)
    results = retriever.search(question, k=4)
    top_score = results[0][1] if results else 0.0

    print("\n[답변]  (오프라인 · API 키 없이 동작)")
    show_sources = True
    if item and fscore >= 0.25:
        print(item["answer"])
        print(f"(출처: {item['source']})")
    elif results and top_score >= 0.10:
        top, _ = results[0]
        print("정확히 일치하는 FAQ가 없어, 가장 관련 높은 규정 조문을 안내합니다:\n")
        print(top.text[:500].rstrip())
        print(f"\n(출처: {top.source})")
    else:
        print("문의하신 내용은 인사관리(근태·공수·복지) FAQ 범위에서 확인되지 않습니다.")
        print("관련 담당 부서에 문의하세요.")
        show_sources = False

    if show_sources and results:
        print("\n[관련 근거 조문]")
        for chunk, score in results:
            print(f"  • ({score:.3f}) {chunk.source}")

    print("\n※ OPENAI_API_KEY를 설정하면 OpenAI가 여러 조문을 종합해 답변·검증합니다.")


# ---------------------------------------------------------------------------
# 단순 모드 (스트리밍, 하네스 없음)
# ---------------------------------------------------------------------------

def answer_simple(client, retriever: Retriever, question: str) -> str:
    results = retriever.search(question, k=4)
    context = build_context(results) if results else "(관련 규정을 찾지 못했습니다.)"

    user_content = (
        f"<근거>\n{context}\n</근거>\n\n"
        f"위 근거만을 바탕으로 다음 질문에 답하세요.\n질문: {question}"
    )

    print("\n어시스턴트: ", end="", flush=True)
    parts: list[str] = []
    stream = client.chat.completions.create(
        model=MODEL,
        max_tokens=4000,
        stream=True,
        messages=[
            {"role": "system", "content": SIMPLE_SYSTEM},
            {"role": "user", "content": user_content},
        ],
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            print(delta, end="", flush=True)
            parts.append(delta)
    print("\n")
    return "".join(parts)


# ---------------------------------------------------------------------------
# 하네스 모드 (3-에이전트 파이프라인, 기본값)
# ---------------------------------------------------------------------------

def answer_with_harness(client, retriever: Retriever, question: str) -> None:
    print("\n[1/3] 규정 검색 중...", flush=True)
    draft, report, results = harness(client, retriever, question)

    print("\n" + "─" * 40)
    print("어시스턴트 (답변 에이전트):\n")
    print(draft)

    print("\n" + "─" * 40)
    print("[검증 에이전트 리포트]\n")
    print(report)
    print()


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------

def main() -> None:
    args = sys.argv[1:]
    offline = "--offline" in args
    simple = "--simple" in args
    args = [a for a in args if a not in {"--offline", "--simple"}]
    one_shot = " ".join(args).strip()

    retriever = Retriever()
    faq = load_faq()
    mode_label = "오프라인" if offline else ("단순" if simple else "하네스(3-에이전트)")
    print(f"인사관리 FAQ 챗봇  (규정 청크 {len(retriever.chunks)}개 | 모드: {mode_label})")

    client = None
    if not offline:
        if not os.environ.get("OPENAI_API_KEY"):
            print("OPENAI_API_KEY가 없어 오프라인 모드로 전환합니다.")
            offline = True
        else:
            from llm import make_client, transport_label
            client = make_client()
            print(f"OpenAI 연동: {transport_label(client)}")

    # 단발 질문
    if one_shot:
        if offline:
            answer_offline(retriever, one_shot, faq)
        elif simple:
            answer_simple(client, retriever, one_shot)
        else:
            answer_with_harness(client, retriever, one_shot)
        return

    # 대화 모드
    print("\n예시 질문:")
    for item in faq["items"][:5]:
        print(f"  - {item['question']}")
    print("\n질문을 입력하세요. (종료: exit / quit / q)\n")

    while True:
        try:
            q = input("나: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n종료합니다.")
            break
        if q.lower() in {"exit", "quit", "q", "종료"}:
            print("종료합니다.")
            break
        if not q:
            continue

        if offline:
            answer_offline(retriever, q, faq)
            print()
        elif simple:
            answer_simple(client, retriever, q)
        else:
            answer_with_harness(client, retriever, q)


if __name__ == "__main__":
    main()
